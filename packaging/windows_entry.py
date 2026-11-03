"""PyInstaller entry point for the Windows build (absolute import, no package context)."""

from smartplug.app import main

raise SystemExit(main())
