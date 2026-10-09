/* Are times shown where the person is, and is "today" today here?

   Runs in whatever time zone this machine is in, and checks the answers
   against that zone rather than against a fixed one — the point is that the
   page follows the person, wherever they are.
       node tools/check_local_time.js
*/

const { boot, reporter } = require("./_jsdom_boot");

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot();
  const off = -new Date().getTimezoneOffset();
  console.log(`this machine is ${off >= 0 ? "+" : ""}${off} minutes from UTC`);

  const stored = "2026-09-25T01:38:00+00:00";
  const shown = window.whenLocal(stored);
  const expected = new Date(stored).toLocaleString(undefined, { day: "numeric",
    month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });
  check("a stored time is shown in local time", shown === expected, shown);
  check("with no raw ISO or UTC in it", !/T\d\d:|UTC/.test(shown));
  check("a stored time without a zone is still read as UTC",
    window.whenLocal("2026-09-25T01:38:00") === expected);
  check("a bare date is shown as the date written, never moved",
    /25/.test(window.niceDate("2026-09-25")) && /Sep/.test(window.niceDate("2026-09-25")));

  const d = new Date();
  const local = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  check("today is today here", window.localToday() === local, `${window.localToday()} vs ${local}`);

  let sent = "";
  const real = window.fetch;
  window.fetch = async (url, opts) => {
    if (String(url).includes("/api/state")) sent = (opts && opts.headers && opts.headers["X-GAIUS-UTC-Offset"]) || "";
    return real(url, opts);
  };
  await window.api("/api/state");
  check("every request says where the person is", sent === String(off), `sent ${sent}`);
  finish(errors, "times follow the person, and today is today where they are");
}

main().catch((e) => { console.error(e); process.exit(1); });
