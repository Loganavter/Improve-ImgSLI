# Multi Compare Tab

Multi Compare is a self-contained workspace tab for comparing several images
in one synchronized scene.

Start with the local documentation:

- [docs/README.md](docs/README.md) - current status and supported workflows
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - state, rendering, overlays,
  export, and coordinate contracts
- [docs/TODO.md](docs/TODO.md) - tab-local backlog

The tab follows the host [Tab Contract](../../../docs/dev/tabs/index.md) but
keeps its own state, translations, resources, renderer passes, and export
helpers under this package.
