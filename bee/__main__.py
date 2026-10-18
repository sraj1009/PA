from .cli import _hard_exit, main

if __name__ == "__main__":
    try:
        _hard_exit(main())
    except SystemExit as e:          # modes that call sys.exit() inside main()
        _hard_exit(e.code)
    except KeyboardInterrupt:        # Ctrl-C at shutdown must still leave
        _hard_exit(130)
