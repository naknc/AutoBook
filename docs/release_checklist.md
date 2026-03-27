# AutoBook Release Checklist

## Product

- Verify catalog search works with at least 3 sample queries.
- Verify library list and grid modes both render correctly.
- Verify queue actions: run, retry, cancel, reorder, clear finished.
- Verify device transfer works with at least one connected device profile.
- Verify OCR runs on a sample PDF.
- Verify conversion runs for `txt -> epub` and one reverse flow.
- Verify analytics screen loads without empty-layout issues.

## Policy

- Review allowed sources and allowed formats.
- Review workspace role and allowed actions.
- Review active device profile and auto-send behavior.

## Files

- Confirm `logs/autobook.log` is being written.
- Confirm `library/companion/library_feed.json` is generated.
- Confirm `library/companion/index.html` opens correctly.

## UX

- Check Turkish and English navigation labels.
- Check onboarding appears only once on fresh settings.
- Check Settings, Library and Search layouts at narrow and wide window sizes.

## Final Smoke Test

- Launch with `uv run main.py`
- Download one book
- Add it to a collection
- Run one OCR/conversion or repair action
- Send one book to device or run device diagnostics
- Open Analytics and Settings once
