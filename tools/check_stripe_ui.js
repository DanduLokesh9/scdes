/* Paying by card: Stripe's Buy Button on the Subscription page.

     1. The Card route offers "Pay by card" — with no test-mode note (taken
        off at the team's request, Oct 2026).
     2. Pressing it raises a card order first.
     3. Then Stripe's button appears, tagged with that order and the payer's
        email — and a plain link to the same page, for when the button cannot
        load.

   Every server answer is held here; nothing is ordered or charged.
       node tools/check_stripe_ui.js
*/

const { boot, settle, until, reporter, openView } = require("./_jsdom_boot");

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot();
  const doc = window.document;
  const posts = [];
  const real = window.fetch;
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (u.includes("/api/billing/order")) {
      posts.push(JSON.parse(opts.body));
      return { ok: true, status: 200, json: async () => ({ ok: true, order: { id: "ORD-test123" } }) };
    }
    if (u.includes("/api/billing")) {
      return { ok: true, status: 200, json: async () => ({ plan: { amount_set: false, term_months: 12 },
        entitlement: {}, orders: [], card_ready: true, override: false,
        stripe: { available: true, test_mode: true, buy_button_id: "buy_btn_TEST",
                  publishable_key: "pk_test_ABC", payment_link: "https://buy.stripe.com/test_LINK" } }) };
    }
    return real(url, opts);
  };

  console.log("the Subscription page");
  check("it opens", await openView(window, "billing", /How to buy it/));
  const view = () => doc.getElementById("view").textContent.replace(/\s+/g, " ");
  check("Card offers Pay by card", !!doc.getElementById("blCard"));
  const explained = [...doc.querySelectorAll("#view p")].find((p) => /Stripe's own secure page/.test(p.textContent));
  check("the button comes before its explanation", !!explained
    && !!(doc.getElementById("blCard").compareDocumentPosition(explained) & window.Node.DOCUMENT_POSITION_FOLLOWING));
  check("with no test-mode note, even on test keys", !/Test mode/.test(view()) && !/4242/.test(view()));
  check("and no purchase-order route", !doc.getElementById("blInvoice") && !/Purchase order/.test(view()));
  check("nothing is ordered before pressing it", posts.length === 0);

  doc.getElementById("blCard").click();
  check("pressing it raises a card order", await until(() => posts.length === 1 && posts[0].route === "card"));
  check("then Stripe's button appears", await until(() => doc.querySelector("stripe-buy-button")));
  const btn = doc.querySelector("stripe-buy-button");
  check("with the CFO's button and key", btn.getAttribute("buy-button-id") === "buy_btn_TEST"
    && btn.getAttribute("publishable-key") === "pk_test_ABC");
  check("tagged with the order, so the payment is matched", btn.getAttribute("client-reference-id") === "ORD-test123");
  check("and the payer's email", btn.getAttribute("customer-email") === "walk@harness.gaius.test");
  check("Stripe's script is loaded once", doc.querySelectorAll('script[src="https://js.stripe.com/v3/buy-button.js"]').length === 1);
  const link = doc.querySelector('#blStripe a[href^="https://buy.stripe.com/"]');
  check("a plain link to the same page, with the order on it", !!link
    && /client_reference_id=ORD-test123/.test(link.getAttribute("href"))
    && /prefilled_email=walk%40harness.gaius.test/.test(link.getAttribute("href")));
  check("which opens safely in a new tab", link && link.getAttribute("target") === "_blank"
    && link.getAttribute("rel") === "noopener");

  window.fetch = real;
  finish(errors, "Pay by card raises an order and hands it to Stripe's button");
}

main().catch((e) => { console.error(e); process.exit(1); });
