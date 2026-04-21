# TBM Chat Widget Integration Guide

## Quick Start

Add this single line to your website, just before the closing `</body>` tag:

```html
<script src="https://your-api-domain.com/widget/chat-widget.js" data-org="your-org-slug"></script>
```

Replace:
- `your-api-domain.com` with the domain where the TBM Chatbot API is hosted
- `your-org-slug` with your organization's slug (provided by your admin)

## Configuration

The widget automatically loads its configuration (colors, logo, welcome message) from the API based on your `data-org` value. No additional configuration is needed in the embed code.

### Optional Attributes

| Attribute   | Description                          | Default                  |
|-------------|--------------------------------------|--------------------------|
| `data-org`  | **Required.** Your organization slug | —                        |
| `data-api`  | API base URL override                | Same origin as widget JS |

## Widget Customization

Widget appearance is managed through the admin API. Contact your administrator to update:

- **Primary color** — Button and header background color
- **Text color** — Button and header text color  
- **Logo URL** — Organization logo shown in the chat header
- **Welcome message** — First message displayed when chat opens
- **Placeholder text** — Input field placeholder

## Features

- Floating chat bubble (bottom-right corner)
- Clean, modern chat interface
- Source citations with clickable links
- Typing indicator during response generation
- Session persistence (conversations maintained within browser session)
- Mobile responsive design
- Lightweight (~15KB JS + ~5KB CSS)
- No framework dependencies (vanilla JavaScript)

## Browser Support

- Chrome 60+
- Firefox 55+
- Safari 11+
- Edge 79+
- iOS Safari 11+
- Chrome for Android 60+
