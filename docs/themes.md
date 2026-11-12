# Themes in Raccontami

A theme sets the colours of the reader and how the spoken word is marked.

## Using themes

Themes are chosen in the reader (**Aa → Theme**) or in **Settings → Look**.

- **Pick a theme**: tap its preview. Each preview shows the theme's own colours.
- **Light or dark**: under **Appearance**, **Auto** follows the phone; **Light** and **Dark** keep one.
- **Add a theme**: tap **Import theme file** and choose a `.json` or `.rtheme` file (see below).
- **Remove a theme you added**: press and hold its preview, or select it and tap
  **Remove the theme**. The themes that come with the app cannot be removed.

## Writing a theme

A theme is a small text file. It holds colours and the highlight style, nothing else.

```json
{
  "format": "raccontami-theme",
  "name": "Lavender Night",
  "light": { "page": "#F3F0F7", "text": "#2B2735", "accent": "#6B4FA0", "highlight": "#6B4FA02E" },
  "dark":  { "page": "#23202B", "text": "#ECE6F4", "accent": "#B79CEB", "highlight": "#B79CEB40" },
  "highlight": { "style": "underline" }
}
```

A complete example, with every colour, is in [`themes/lavender-night.json`](themes/lavender-night.json):
copy it, change the name and the colours, and import it.

| Field | Meaning |
|---|---|
| `name` | Required. Shown under the preview. Importing a theme with the same name replaces the earlier one. |
| `light`, `dark` | The colours for light and for dark. At least one; if one is missing, the other is used for both. |
| `highlight.style` | How the spoken word is marked: `fill` (the default), `underline`, `outline`, or `text` (the word changes colour). |
| `highlight.radius` | How round the corners of `fill` and `outline` are. The default is nearly square. |
| `format` | `"raccontami-theme"`. Any other value is refused. |
| `author` | Optional, free text. |

### Colours

Colours are written `#RRGGBB`, or `#RRGGBBAA` to make them see-through (the last two digits, as in
CSS). Every colour is optional: one that is missing is taken from the built-in theme Alessandrite.

| Colour | Used for |
|---|---|
| `page` | The background of the text. |
| `text` | The text of the book. |
| `accent` | The play button, progress, selected items, and the `underline` and `outline` highlight. |
| `highlight` | The background of the spoken word with the `fill` style. Make it see-through. |
| `surface` | Panels and sheets. |
| `raised` | Buttons, chips, the part of the progress bar not yet played. |
| `line` | Thin borders. |
| `textMuted` | Secondary text. |
| `textFaint` | The least important labels. |
| `untimedText` | Text that is never read aloud (front matter, captions). |
| `danger` | Errors and delete buttons. |

## Tips

- The first four colours do most of the work: start with `page`, `text`, `accent` and `highlight`.
- Keep `highlight` see-through (last two digits between `2E` and `47`), so the word stays readable under it.
- If the theme has both `light` and `dark`, look at it in both: **Aa → Appearance**.
