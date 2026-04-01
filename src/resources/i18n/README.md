# Translation Structure

Translations are stored per language directory:

```text
src/resources/i18n/
  en/
  ru/
  pt_BR/
  zh/
```

Each language directory may contain nested folders with multiple JSON files. Files are merged recursively at runtime.

## Conventions

- Keep one concern per file.
- Use nested JSON objects, not flat dotted keys inside files.
- Keep the runtime lookup API as dotted keys, for example `tr("common.ok")`.
- Prefer stable semantic keys over sentence-shaped identifiers for new entries.
- Put generic shared strings under `shared/` or `ui/`.
- Put feature-specific strings under `features/` or another feature folder.

## Validation

Run:

```bash
python3 tools/validate_translations.py
```

The validator checks:

- all language packs expose the same flattened key set
- keys referenced via `tr("...")` exist
- unused keys in the reference language are reported
