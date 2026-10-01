# Sending the verification code

The platform emails a six-digit code and refuses to let anyone in until it comes
back. Until SMTP is configured it shows the code on screen instead — usable for
a demo, but it verifies nothing, so this needs doing before real agencies
register.

---

## Where it stands, as of 26 August 2026

Checked from outside the account, because there are no AWS credentials on this
machine. `governingai.us` is on GoDaddy (`ns03/ns04.domaincontrol.com`).

**Confirmed by DNS lookup:**

| Record | State | Consequence |
|---|---|---|
| SPF (`TXT`) | **absent** | Nothing authorises any host to send as this domain |
| MX | **absent** | The domain cannot receive mail — fine for sending only |
| DMARC | `v=DMARC1; p=quarantine` | Mail failing both SPF and DKIM gets quarantined |

**Not checkable from here:** whether the three SES DKIM `CNAME`s exist. They
live at `<token>._domainkey.governingai.us`, and the tokens are only visible
inside the SES console — so "no DKIM records found" cannot be concluded, and an
earlier note in this project claiming DNS was confirmed correct should not be
relied on.

**What this means.** The DMARC policy is already `quarantine` while no SPF
record exists, so even if DKIM verifies, anything that fails DKIM alignment
lands in a spam folder rather than bouncing visibly — which is the failure that
looks like "the code never arrived" with nothing in any log to explain it. SPF
needs adding whichever route is taken.

**One pass to unblock it:**

1. SES console → *Verified identities* → `governingai.us` → **DKIM**. Either
   copy the three CNAME name/value pairs, or note that the identity is not
   there at all.
2. GoDaddy → DNS for `governingai.us` → confirm those three CNAMEs exist
   exactly, including the `._domainkey` suffix. GoDaddy appends the domain
   automatically, so pasting the fully-qualified name is the usual mistake.
3. Add SPF as a `TXT` record on the root. Whichever route you take, exactly one
   of these — two SPF records on one domain is a permanent error, not a merge:

   | Route | Host | Value |
   |---|---|---|
   | Amazon SES | `@` | `v=spf1 include:amazonses.com ~all` |
   | SendGrid | `@` | `v=spf1 include:sendgrid.net ~all` |
   | Both, during a switchover | `@` | `v=spf1 include:amazonses.com include:sendgrid.net ~all` |

4. SES starts in the sandbox: it will only send to addresses you have also
   verified. **Request production access** in the console, which is a separate
   step from verifying the domain and takes about a day.

Until step 4 clears, a real `.gov` address cannot receive a code no matter how
correct the DNS is.

**The application's own send path is already proven.** `tools/check_mail.py`
drives `app/mailer.py` through a real SMTP conversation — envelope, login,
headers, both body parts, the DATA leg and the failure path — against a local
sink. It passes. So when a code fails to arrive after this is configured, the
cause is credentials or DNS, not the platform, and that check is how to tell
the difference quickly.

The one leg it does not exercise is the TLS upgrade itself, because generating a
certificate needs tooling this machine does not have. That is three lines of
stdlib and gets its first real run in the SES sandbox.

Two routes. **SendGrid** gets it working in about ten minutes. **Amazon SES** is
the better long-term home because the server already lives in AWS, but it starts
restricted and needs a day for approval. Doing SendGrid now and SES later is a
perfectly reasonable order.

---

## Route A — SendGrid (fastest)

1. Sign up at **sendgrid.com** — the free tier sends 100 emails a day, which is
   ample for registrations.
2. **Settings → Sender Authentication → Authenticate Your Domain.** Choose
   GoDaddy, enter `governingai.us`. SendGrid gives you three CNAME records.
3. Add those three records in **GoDaddy → My Products → DNS** for
   `governingai.us`. Takes a few minutes to verify.
4. **Settings → API Keys → Create API Key**, with *Restricted Access → Mail
   Send*. Copy it — it is shown once.
5. On the server:

```
sudo install -m 600 /dev/null /etc/governingai.env
sudo nano /etc/governingai.env
```

```
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=SG.your-key-here
SMTP_FROM=no-reply@governingai.us
SMTP_FROM_NAME=Governing AI
```

`SMTP_USER` is the literal word `apikey` — not your username. That trips
everyone up once.

```
sudo systemctl restart governingai
```

---

## Route B — Amazon SES (better long-term)

Same AWS account as the server, and around **$0.10 per thousand emails**.

1. AWS Console → **Amazon SES** → region **US East (N. Virginia)**, the same as
   the instance.
2. **Verified identities → Create identity → Domain** → `governingai.us`, with
   **Easy DKIM** on.
3. SES gives three CNAME records. Add them in **GoDaddy → DNS**. Verification
   usually completes within the hour.
4. **Request production access.** New SES accounts are sandboxed and can only
   send to addresses you have verified — which would block every real agency.
   Account dashboard → *Request production access*, describe the use (one
   transactional verification email per registration). Approval is typically
   within 24 hours.
5. **SMTP settings → Create SMTP credentials.** These are *not* your AWS access
   keys; SES mints a separate username and password.
6. Same `/etc/governingai.env`, with:

```
SMTP_HOST=email-smtp.us-east-1.amazonaws.com
SMTP_PORT=587
SMTP_USER=<SES SMTP username>
SMTP_PASSWORD=<SES SMTP password>
SMTP_FROM=no-reply@governingai.us
SMTP_FROM_NAME=Governing AI
```

---

## Checking it works

```
sudo systemctl restart governingai
curl -s localhost:8765/api/tenancy | python3 -m json.tool | grep -i deliver
```

Then register on the TEST agency with an `@iiac.ai` address. If the code arrives
by email rather than appearing on screen, it is working.

If the API still reports SMTP unconfigured, the service has not picked up the
file — check `sudo systemctl show governingai | grep EnvironmentFile` and that
the file has no quotes around the values.

---

## Two things worth knowing

**Deliverability.** Government mail servers are strict. Without the DKIM records
in step 3, codes will land in spam and the registration flow will look broken
rather than blocked. Domain authentication is the step to not skip. Once it is
set up, send yourself one and check the headers say `dkim=pass`.

**Never put credentials in the repository.** `/etc/governingai.env` is mode 600
and read by systemd at start. The unit file references it with a leading dash,
so the service still starts if the file is missing — it simply falls back to
showing codes on screen, and the interface says so rather than failing silently.
