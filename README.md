# Solar Quotation Tool (POC)

A Streamlit web app for solar/renewables sales consultants. Enter a UK
postcode, trace the usable south-facing roof on a satellite map, and get
an instant panel/wattage estimate plus a customer-facing quote (purchase
or rental).

## How it works

1. **Postcode lookup** — uses [postcodes.io](https://postcodes.io), a free
   public API, no key required.
2. **Roof tracing** — a satellite map (Esri World Imagery, free tile
   layer) with a draw tool. The consultant draws a rectangle over the
   usable south-facing roof section by eye.
3. **Panel & wattage calculation** — the traced area is converted to a
   panel count and total system wattage using the panel spec in
   `config.json`.
4. **Quote** — shows both a one-off purchase price and a monthly rental
   price over a fixed term.
5. **Admin panel** — password-protected (sidebar → "Admin Panel"). Lets a
   consultant update panel specs, per-panel cost, install cost, rental
   rate, term length, and commission, plus change the admin password.

This is deliberately a POC: roof size is a manual visual estimate, not an
automated satellite measurement (e.g. Google Solar API). That keeps it
free to run and reliable across the whole UK. Automated estimation can be
added later as an enhancement once the tool has proven itself.

## Local setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploying to Streamlit Community Cloud

1. Push this folder to a GitHub repo.
2. Go to [share.streamlit.io](https://share.streamlit.io), connect the
   repo, and set the main file to `app.py`.
3. That's it — no secrets or API keys are required for this POC, since
   postcodes.io and the Esri satellite tiles are both free/keyless.

## Admin panel

- Default password: `solar123` — **change this before sharing the link
  with anyone**, via the admin panel itself (it re-hashes and saves back
  to `config.json`).
- All settings are stored in `config.json` in plain JSON, so you can also
  hand-edit defaults directly and commit them to the repo.

> Note: on Streamlit Community Cloud, writes to `config.json` only
> persist for the life of the running app instance — a redeploy or app
> restart will reset it to whatever's committed in the repo. For a
> proof of concept this is fine; if this becomes a permanent tool later,
> settings should move to Streamlit's secrets manager or a small database
> (this is the same next-step pattern used in the Novalink telecoms
> platform).

## Roadmap ideas (post-POC)

- Swap manual roof tracing for the Google Solar API once UK coverage is
  confirmed good enough in your sales areas — it can return roof
  segments, orientation, and panel/wattage estimates automatically.
- PDF quote generation and email delivery (same pattern as the Novalink
  telecoms paperwork suite).
- Persistent settings storage (database or Streamlit secrets) instead of
  a JSON file, so admin changes survive app restarts.
