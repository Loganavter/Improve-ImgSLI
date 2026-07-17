# Help Widget (toolkit helpers)

Live Help UI is documented in [HELP_SYSTEM.md](./HELP_SYSTEM.md)
(`plugins/help/` + tab `contribute_help` + `HelpDocumentView`).

The toolkit still ships `MarkdownHelpDialog` / `QTextBrowser` helpers for
compatibility and unit tests (`ensure_heading_ids`, `build_page_toc`). New
illustrated docs must use `HelpDocumentView`, not `QTextBrowser`.
