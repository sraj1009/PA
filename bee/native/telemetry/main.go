// bee-telemetry — BEE's native system-stats daemon (Go, standard library only).
//
// Why: BEE's Python side used to spawn PowerShell + CIM/WMI on EVERY stat read,
// which is slow (especially under low free RAM). This daemon stays resident and
// reads Windows metrics directly through the OS API, served on localhost HTTP.
// BEE queries it in ~1 ms; if it is down, BEE falls back to the original
// PowerShell path, so this is a pure speed-up with no regression.
//
// Build:  go build -o bee-telemetry.exe .
// Run:    bee-telemetry.exe -addr 127.0.0.1:8790
// API:
//   GET /stats?[disk=D:\]  -> {cpu_pct, ram_*, disk_*, uptime_s, ...}
//   GET /health            -> {"ok":true,"uptime_s":...}
package main

import (
	"encoding/json"
	"flag"
	"log"
	"math"
	"net"
	"net/http"
	"os"
	"runtime"
	"sync"
	"syscall"
	"time"
	"unsafe"
)

const (
	mb = 1 << 20
	gb = 1 << 30
)

// ---- Windows native metrics (syscall = stdlib; LazyDLL keeps it version-safe)

type filetime struct{ lo, hi uint32 }

func ftVal(f *filetime) uint64 { return uint64(f.hi)<<32 | uint64(f.lo) }

var (
	kernel32               = syscall.NewLazyDLL("kernel32.dll")
	procGetSystemTimes     = kernel32.NewProc("GetSystemTimes")
	procGlobalMemoryStatus = kernel32.NewProc("GlobalMemoryStatusEx")
	procGetDiskFreeSpaceEx = kernel32.NewProc("GetDiskFreeSpaceExW")
	procGetTickCount64     = kernel32.NewProc("GetTickCount64")
	procGetSystemPowerStat = kernel32.NewProc("GetSystemPowerStatus")
)

func sysTimes() (idle, kernel, user uint64) {
	var i, k, u filetime
	r, _, _ := procGetSystemTimes.Call(
		uintptr(unsafe.Pointer(&i)),
		uintptr(unsafe.Pointer(&k)),
		uintptr(unsafe.Pointer(&u)))
	if r == 0 {
		return 0, 0, 0
	}
	return ftVal(&i), ftVal(&k), ftVal(&u)
}

// MEMORYSTATUSEX (dwLength must equal the struct size in bytes).
type memStatusEx struct {
	dwLength             uint32
	dwMemoryLoad         uint32
	ullTotalPhys         uint64
	ullAvailPhys         uint64
	ullTotalPageFile     uint64
	ullAvailPageFile     uint64
	ullTotalVirtual      uint64
	ullAvailVirtual      uint64
	ullAvailExtVirtual   uint64
}

func getRam() (totalMB, freeMB, loadPct float64) {
	var m memStatusEx
	m.dwLength = uint32(unsafe.Sizeof(m))
	r, _, _ := procGlobalMemoryStatus.Call(uintptr(unsafe.Pointer(&m)))
	if r == 0 {
		return 0, 0, 0
	}
	return float64(m.ullTotalPhys) / mb, float64(m.ullAvailPhys) / mb, float64(m.dwMemoryLoad)
}

func getDisk(root string) (totalGB, freeGB float64) {
	w, err := syscall.UTF16PtrFromString(root)
	if err != nil {
		return 0, 0
	}
	var free, total, totalFree uint64
	r, _, _ := procGetDiskFreeSpaceEx.Call(
		uintptr(unsafe.Pointer(w)),
		uintptr(unsafe.Pointer(&free)),
		uintptr(unsafe.Pointer(&total)),
		uintptr(unsafe.Pointer(&totalFree)))
	if r == 0 {
		return 0, 0
	}
	return float64(total) / gb, float64(free) / gb
}

func uptimeS() float64 {
	ms, _, _ := procGetTickCount64.Call()
	return float64(ms) / 1000.0
}

// SYSTEM_POWER_STATUS (Go inserts the same alignment padding as the C struct).
type systemPowerStatus struct {
	acLine     byte
	batFlag    byte
	batPct     byte
	sysFlag    byte
	batLife    uint32
	batFull    uint32
}

func getBattery() (pct, ac int, hasBattery bool) {
	var s systemPowerStatus
	r, _, _ := procGetSystemPowerStat.Call(uintptr(unsafe.Pointer(&s)))
	if r == 0 {
		return -1, -1, false
	}
	if s.batFlag&0x80 != 0 { // 0x80 = battery absent (desktop / AC power)
		return -1, int(s.acLine), false
	}
	acv := int(s.acLine) // 0 = on battery, 1 = AC plugged in, 255 = unknown
	if acv == 255 {
		acv = -1
	}
	return int(s.batPct), acv, true
}

// CPU busy % from the delta between two GetSystemTimes samples.
// kernelTime already includes idle, so busy = (kernel - idle) + user.
type sample struct{ idle, kernel, user uint64 }

func cpuPct(prev, cur sample) float64 {
	idleD := cur.idle - prev.idle
	kernelD := cur.kernel - prev.kernel
	userD := cur.user - prev.user
	totalD := kernelD + userD
	if totalD == 0 {
		return 0
	}
	busyD := (kernelD - idleD) + userD
	return 100.0 * float64(busyD) / float64(totalD)
}

func round1(x float64) float64 { return math.Round(x*10) / 10 }
func round2(x float64) float64 { return math.Round(x*100) / 100 }

// ---- HTTP

var (
	mu          sync.Mutex
	last        sample
	hostName, _ = os.Hostname()
)

func statsHandler(w http.ResponseWriter, r *http.Request) {
	root := r.URL.Query().Get("disk")
	if root == "" {
		root = "C:\\"
	}
	mu.Lock()
	i, k, u := sysTimes()
	now := sample{i, k, u}
	cpu := cpuPct(last, now)
	last = now
	mu.Unlock()

	totalMB, freeMB, load := getRam()
	totalGB, freeGB := getDisk(root)
	batPct, batAC, hasBat := getBattery()

	out := map[string]any{
		"cpu_pct":       round2(cpu),
		"ram_free_mb":   round1(freeMB),
		"ram_total_mb":  round1(totalMB),
		"ram_pct":       round1(load),
		"disk_free_gb":  round1(freeGB),
		"disk_total_gb": round1(totalGB),
		"disk_root":     root,
		"uptime_s":      round1(uptimeS()),
		"host":          hostName,
		"ts":            time.Now().Unix(),
		"native":        runtime.Version(),
	}
	if hasBat {
		out["battery_pct"] = batPct
		out["battery_ac"] = batAC
	} else {
		out["battery_pct"] = -1
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(out)
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"ok": true, "uptime_s": round1(uptimeS())})
}

func main() {
	addr := flag.String("addr", "127.0.0.1:8790", "listen address")
	flag.Parse()

	i, k, u := sysTimes()
	last = sample{i, k, u}

	mux := http.NewServeMux()
	mux.HandleFunc("/stats", statsHandler)
	mux.HandleFunc("/health", healthHandler)

	ln, err := net.Listen("tcp", *addr)
	if err != nil {
		// Port already owned by another bee-telemetry instance -> exit cleanly.
		log.Printf("listen %s: %v (another instance may already be running); exiting", *addr, err)
		return
	}
	log.Printf("bee-telemetry listening on http://%s  (native %s, host %s)", *addr, runtime.Version(), hostName)
	if err := http.Serve(ln, mux); err != nil {
		log.Printf("server: %v", err)
	}
}
