/* View as — the bar, the button, and the way out.

     1. Organizations shows View as next to each person in an active organization.
     2. Choosing it asks first, saying it is view only and they are not told.
     3. While viewing, a bar across the top says who, which organization, and
        "view only", with End impersonation — and the admin menu is gone.
     4. End impersonation ends it.

   Every server answer is held here; nothing is written.
       node tools/check_impersonate_ui.js
*/

const { boot, settle, until, reporter, openView } = require("./_jsdom_boot");

const ORGS = { ok: true, waiting: 0, pending: [], organizations: [
  { agency: "sc.ed", organization: "South Carolina Department of Education", state: "SC",
    status: "active", created_at: "", test: false, needs_admin: false,
    people: [{ email: "jane.smith@ed.sc.gov", name: "Jane Smith", title: "Director", role: "admin", added_at: "" }] }] };

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot();
  const doc = window.document;
  const posts = [];
  const real = window.fetch;
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (opts && opts.method === "POST") posts.push(u.replace(/^.*\/api/, "/api").split("?")[0]);
    if (u.includes("/api/admin/organizations")) return { ok: true, status: 200, json: async () => ORGS };
    if (u.includes("/api/admin/impersonate/")) return { ok: true, status: 200, json: async () => ({ ok: true }) };
    return real(url, opts);
  };

  console.log("Organizations");
  check("it opens", await openView(window, "organizations", /All organizations/));
  doc.querySelector("details.org-row") && doc.querySelector("details.org-row").setAttribute("open", "");
  const viewAs = doc.querySelector('[data-viewas="jane.smith@ed.sc.gov"]');
  check("View as sits next to the person", !!viewAs && /View as Jane Smith, view only/.test(viewAs.getAttribute("aria-label")));
  viewAs.click();
  await settle(100);
  const veil = (doc.getElementById("confirmVeil") || {}).textContent || "";
  check("it asks first, and says view only and not told", /View as Jane Smith\?/.test(veil)
    && /view only/.test(veil) && /not told/.test(veil));
  check("nothing is sent before the answer", !posts.includes("/api/admin/impersonate/start"));
  doc.getElementById("confirmYes").click();
  check("then it starts", await until(() => posts.includes("/api/admin/impersonate/start")));

  console.log("\nwhile viewing");
  window.impersonationBar({ impersonating: { name: "Jane Smith", title: "Director",
    email: "jane.smith@ed.sc.gov", organization: "South Carolina Department of Education",
    since: "2026-10-01T10:00:00+00:00", says: "" } });
  const bar = doc.getElementById("impBar");
  check("a bar says who, where, and view only", !!bar && /Viewing as Jane Smith/.test(bar.textContent)
    && /South Carolina Department of Education/.test(bar.textContent) && /view only/.test(bar.textContent));
  check("it is the first thing on the page", doc.body.firstElementChild === bar);
  check("it is a named region", bar.getAttribute("role") === "region" && bar.getAttribute("aria-label") === "Impersonation");
  check("the header names their organization", /Department of Education/.test(doc.getElementById("agencyCrumb").textContent));
  bar.querySelector("#impEnd").click();
  check("End impersonation ends it", await until(() => posts.includes("/api/admin/impersonate/stop")));
  window.impersonationBar({ impersonating: null });
  check("and the bar goes", !doc.getElementById("impBar"));

  window.fetch = real;
  // jsdom cannot reload a page; the real browser does.
  finish(errors.filter((e) => !/Not implemented: navigation/.test(e)),
         "View as is offered, asked, shown, and ended");
}

main().catch((e) => { console.error(e); process.exit(1); });
