# Optional reading appearance

Existing installations keep the current UI. Set `READER_APPEARANCE_ENABLED=true`
to add Appearance to the account control. No database migration is required.

Users can choose a local font for the entire interface, with serif and sans-serif
samples. Preferences stay in this browser. Theme default clears a font override;
Device default clears a theme override. Storage denial still permits a choice for
the current page. Other browsers retain their own choices.

Register optional local CSS overlays through environment configuration:

```dotenv
READER_APPEARANCE_ENABLED=true
READER_THEMES={"paper":{"label":"Paper","stylesheet":"css/paper.css"}}
READER_THEME_DESKTOP=classic
READER_THEME_MOBILE=paper
```

Make `aggregator/static/css/paper.css` available on each web replica. Stylesheets
must be local `css/*.css` files. This setting does not upload files or load a CDN.
An omitted mobile default follows the desktop default. Unknown defaults refuse
startup; a removed browser choice falls back to the device default. The existing
Light/Dark control remains independent. Custom styles should use theme.css tokens
and work in both appearances, with visible keyboard focus and narrow viewports.
A failed stylesheet falls back to the original appearance and displays a message
in Appearance. Reload to retry the selected stylesheet. Custom CSS is trusted
operator code and can import resources; only install stylesheets you trust.

The feature changes presentation only. It does not change selection, grouping,
provider configuration, access control, feeds, or inference usage.
