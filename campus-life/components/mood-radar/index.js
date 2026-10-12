const { polygon } = require('../../core/moodscore');

Component({
  properties: {
    axes: { type: Array, value: [], observer: 'recompute' },
    size: { type: Number, value: 520, observer: 'recompute' },
    pad: { type: Number, value: 96, observer: 'recompute' },
  },

  data: {
    points: [],
    edges: [],
    spokes: [],
    rings: [],
    center: 260,
    maxR: 164,
  },

  methods: {
    recompute() {
      const rows = this.properties.axes || [];
      const size = this.properties.size || 520;
      const pad = this.properties.pad == null ? 96 : this.properties.pad;
      const geo = polygon(rows, { size, pad });
      this.setData({
        points: geo.points,
        edges: geo.edges,
        spokes: geo.spokes,
        center: geo.center,
        maxR: geo.maxR,
        rings: [0.25, 0.5, 0.75, 1].map((f) => geo.maxR * f),
      });
    },
  },

  lifetimes: {
    attached() {
      this.recompute();
    },
  },
});
