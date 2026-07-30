# ChurchHub Marketing Website

Static HTML marketing site (no build step).

## Pages

| Page | File |
|------|------|
| Landing | [`index.html`](./index.html) |
| Features | [`features.html`](./features.html) |
| Pricing | [`pricing.html`](./pricing.html) |
| FAQ | [`faq.html`](./faq.html) |
| Contact | [`contact.html`](./contact.html) |
| Testimonials (placeholders) | [`testimonials.html`](./testimonials.html) |
| Product comparisons | [`compare.html`](./compare.html) |

Shared assets: `assets/css/site.css`, `assets/js/site.js`

## Preview locally

```bash
cd churchhub/marketing/website
python -m http.server 5500
```

Open http://127.0.0.1:5500/

## Before public launch

1. Replace `*@churchhub.example` with real inboxes.
2. Wire the contact form to your CRM / email endpoint.
3. Swap testimonial placeholders for approved quotes (remove Placeholder badges).
4. Fill pricing `$___` when commercial packaging is final.
5. Drop real product screenshots into the landing/features sections when ready.
