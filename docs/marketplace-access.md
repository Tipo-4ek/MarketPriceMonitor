# What marketplaces actually serve to an automated client

Measured in July 2026, from two different networks: a residential connection and
a datacenter VM on an unrelated subnet. Every line below is something that was
run, not something that was read in an article.

This exists because the interesting question for a price tracker is not "how do I
parse HTML" but "will the page arrive at all", and the answer differs per site in
ways that decide the whole design.

## Transport: what gets a page

| Client | Wildberries | DNS | Ozon | Yandex.Market | AliExpress | Avito |
| --- | --- | --- | --- | --- | --- | --- |
| `curl` / `requests` | 403 | 401 Qrator | 403 | 302 | 200 + `x5sec` punish | 429 + captcha |
| `curl_cffi`, 6 browser TLS fingerprints | — | — | 403 (18/18) | — | — | — |
| Bundled Chromium, headless | 498 | — | challenge | — | — | — |
| Bundled Chromium, headed | — | — | challenge | — | — | — |
| Real Chrome, headed, cold profile | 498 | 401 | captcha | captcha | captcha | — |
| **Real Chrome, headed, warm profile** | **200** | **200** | captcha | captcha | captcha | — |

Two conclusions the code is built on:

**A real browser is the only transport that works anywhere.** TLS impersonation
is not enough: `curl_cffi` was tried against Ozon impersonating Chrome 110, 120,
124 and 131, Safari 17 and Firefox 133, across three endpoints — all eighteen
combinations returned 403 with a JavaScript challenge page. Mobile-app hosts
(`api.ozon.ru`, `xapi.ozon.ru`) with the app's own headers answered 403 and 402.

**The browser profile is the asset, not the IP.** A cold profile is refused even
from an address that has never contacted the site; the same profile, once it has
been through the transparent challenge, is served normally. This is why
`BROWSER_PROFILE_DIR` must survive restarts, and why the first fetch after a
fresh deploy is slow and may fail.

A corollary worth stating because it contradicts the obvious guess: a datacenter
IP was **not** the problem. Wildberries and DNS both work from the VM.

## Headless, and the server case

Both working sites reject headless — including headless *real* Chrome, not just
Playwright's bundled Chromium. That looked like it confined the project to a
desktop, but it does not: under a virtual framebuffer (`xvfb-run`) a headless
server runs a headed browser and both sites are served normally. That is how the
VM deployment works.

## Where the price hides

Having got a page, the price is in a different place on each site, which is why
the provider abstraction reads through a chain of strategies rather than one
hard-coded path.

| Site | JSON-LD `offers.price` | Internal JSON API | Rendered DOM | Document title |
| --- | --- | --- | --- | --- |
| Wildberries | no | **yes** (`/u-card/cards/v4/detail`, kopecks) | yes | **yes** ("купить за 558 ₽") |
| DNS | **yes** | — | yes | no |
| Ozon | yes (regular price, not the card price) | 403 even from the page's own context | yes, 3 figures + a unit rate | no |

Details that cost time to discover:

- Wildberries' card API refuses a direct call — with `curl`, and even with
  `fetch()` from the product page's own context. The response the page makes for
  itself succeeds, so the provider reads that instead of replaying it.
- Ozon renders three prices together (card price, regular price, struck-through
  old price) plus a unit rate like "218 ₽ за 100 гр". Position alone is not
  enough to tell them apart on cards that lack one of them, so the reader refuses
  ambiguous shapes instead of guessing: a price out by a factor of two is worse
  than a missed poll.
- DNS publishes a sitemap index of 124 sub-sitemaps, 10 000 product URLs each,
  which is the site's own supported way to enumerate the catalogue.

## Why Ozon is not shipped

Ozon serves a **captcha** — an explicit human-verification challenge — and, to
its API hosts, a structured block record naming an incident:

```json
{"incidentId": "fab_…", "blockURL": "…/block.html?…&bm=block_2",
 "supportURL": "…/complaint/support/?incident_id=…", "timeoutSec": 180}
```

Getting an automated client past that is circumventing an access control, not
finding a compatible configuration, so this project does not attempt it — with
stealth-patched browsers, proxy rotation or captcha-solving services alike. It
was verified that a virgin IP on an unrelated subnet is challenged on its first
request, so this is not an individual block that a different address would avoid:
the site refuses automated browsers as a class.

The provider was therefore removed from the registry rather than shipped as code
that always fails. Legitimate routes to Ozon data, if you need them, are the
Seller API for your own listings, or a licensed data provider.

## robots.txt, checked per site

Access rules are only half the question; permission is the other half.

- **DNS** — `User-agent: *` has `Allow: /` plus explicit allows for `/product/*`
  subpaths, no named-crawler denials, no crawl-delay, and a published sitemap.
- **Wildberries** — product paths are not disallowed.
- **Ozon** — every domain refused an automated client outright, so the question
  did not arise.
- **detmir.ru** — product paths are not disallowed, but the site denies
  `MegaIndex` and `DataForSeoBot` by name, which reads as a clear position on
  bulk data collection. Not used for that reason, despite being technically open.

## Method notes

Two mistakes worth recording, because both produced confident wrong answers
before being caught:

- Substring-matching a page for `captcha` gives false positives. DNS product
  pages contain `getCaptchaConfiguration` and `"Вы_не_робот"` inside a
  localisation bundle for the login and feedback forms. Arrival must be decided
  by the presence of the product, not by the absence of a word.
- Comparing browser configurations with fresh profiles compares profile warmth,
  not the configurations. An A/B test of the automation shim was inconclusive for
  exactly this reason and is still open.
