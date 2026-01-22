# Shopify VAT Invoice Scraper

FastAPI microservice that downloads VAT invoice PDFs from Shopify Admin via browser automation.

## The Problem (a.k.a. Why Does This Exist?)

If you're an EU merchant on Shopify, you've probably discovered the *wonderful* situation:

🎉 **Shopify generates VAT invoices!** Great!  
😐 **But there's no API to download them.** Wait, what?  
🤯 **The only URLs expire after 15 days AND have a 5-view limit.** ...Shopify, are you okay?

That's right—in 2026, a $100B+ company that processes billions in e-commerce transactions doesn't provide a GraphQL endpoint for VAT invoices. You can query orders, products, customers, fulfillments, even *draft orders*... but the legally-required tax documents? Nope. 🙃

**Your options:**
1. Click through Admin UI manually for each invoice (enjoy your carpal tunnel)
2. Use the `statusPageUrl` from GraphQL (expires in 15 days, max 5 views per order)
3. **This tool** (browser automation that actually works)

We built this because option 1 is insane and option 2 is useless for any real accounting workflow. Now you don't have to.

## Quick Start

```bash
# Clone and setup
git clone <repo> && cd shopify-invoice-scraper
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt && python -m camoufox fetch

# Configure (required: set your store slug)
cp .env.example .env && sed -i 's/your-store-slug/YOUR-ACTUAL-STORE/' .env

# Run
python -m src.main
```

On first run, a browser opens → log in to Shopify → session persists for future runs.

## Configuration

All settings via environment variables (see `.env.example`):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STORE_SLUG` | ✅ | - | Your store ID from `admin.shopify.com/store/STORE_SLUG` |
| `TIMEZONE` | | `UTC` | For organizing downloads by date |
| `PORT` | | `8000` | API server port |
| `HEADLESS` | | `false` | Must be `false` for first login |

<details>
<summary>All configuration options</summary>

```env
STORE_SLUG=my-store              # Required
ADMIN_BASE_URL=https://admin.shopify.com
PROFILE_DIR=./.browser-profile
DOWNLOAD_DIR=./downloads
SCREENSHOT_DIR=./screenshots
TIMEZONE=UTC
HEADLESS=false
TIMEOUT_PAGE_LOAD=60000
TIMEOUT_SELECTOR=30000
RETRY_ATTEMPTS=3
RETRY_DELAY=2.0
HUMAN_DELAY_MIN=0.5
HUMAN_DELAY_MAX=2.0
HOST=0.0.0.0
PORT=8000
```
</details>

## API

### Core Endpoints

```bash
# Health check
curl localhost:8000/health

# Check/establish session (opens browser if needed)
curl -X POST localhost:8000/session/check

# Signal login complete (after manual login)
curl -X POST localhost:8000/session/login-complete

# Scrape single invoice
curl -X POST localhost:8000/scrape-invoice \
  -H "Content-Type: application/json" \
  -d '{"order_id": "12237732118863", "order_name": "#8512"}'

# Scrape batch
curl -X POST localhost:8000/scrape-batch \
  -H "Content-Type: application/json" \
  -d '{"orders": [{"order_id": "123...", "order_name": "#8512"}]}'
```

### Response

```json
{
  "success": true,
  "shopify_order_id": "12237732118863",
  "order_name": "#8512",
  "invoice_number": "INV-DE-6102",
  "filepath": "./downloads/2024-01-22/INV-DE-6102.pdf",
  "needs_login": false
}
```

When `needs_login: true` → browser window opens for re-auth → call `/session/login-complete` after.

### Other Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Status, session info, browser state |
| `/session/status` | GET | Current session status |
| `/session/check` | POST | Verify login, opens browser if needed |
| `/session/login-complete` | POST | Signal manual login done |
| `/scrape-invoice` | POST | Download single invoice |
| `/scrape-batch` | POST | Download multiple invoices |
| `/browser/idle` | POST | Show status page in browser |
| `/browser/close` | POST | Close browser completely |
| `/cancel` | POST | Cancel current operation |
| `/reset` | POST | Reset cancellation flag |

## Integration Example (Python)

```python
import httpx

BASE = "http://localhost:8000"

# Ensure logged in
r = httpx.post(f"{BASE}/session/check")
if r.status_code == 401:
    input("Log in via browser, then press Enter...")
    httpx.post(f"{BASE}/session/login-complete")

# Scrape
r = httpx.post(f"{BASE}/scrape-invoice", json={"order_id": "123...", "order_name": "#8512"})
print(r.json())
```

## Real-World Integration: Symfony + JavaScript

We built this for a Symfony app that needed automated invoice downloads. Here's a condensed overview of the key patterns that solved the tricky problems:

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Symfony Backend                                             │
│  ├── ShopifyVatInvoiceService  →  GraphQL for order list    │
│  ├── ShopifyInvoiceController  →  API endpoints             │
│  └── ShopifyVatInvoice Entity  →  Tracks download status    │
└─────────────────────────────────────────────────────────────┘
                              ↓ HTTP
┌─────────────────────────────────────────────────────────────┐
│  JavaScript (Twig template)                                  │
│  └── Orchestrates: fetch orders → scrape → save results     │
└─────────────────────────────────────────────────────────────┘
                              ↓ HTTP (localhost:8000)
┌─────────────────────────────────────────────────────────────┐
│  This Python Scraper                                         │
│  └── Browser automation, PDF download                       │
└─────────────────────────────────────────────────────────────┘
```

### Problem 1: Session Management Across Requests

The scraper might need re-login mid-batch. Solution: check before each request, pause UI if needed.

```javascript
async function ensureSession() {
    const r = await fetch('http://localhost:8000/session/check', { method: 'POST' });
    if (r.status === 401) {
        showLoginPrompt();  // Show "Please log in" UI
        return false;
    }
    return true;
}

async function processOrders(orders) {
    for (const order of orders) {
        if (!await ensureSession()) {
            await waitForLoginSignal();  // User clicks "Login Complete" button
        }
        const result = await scrapeInvoice(order);
        await saveResult(result);  // POST to Symfony backend
    }
}
```

### Problem 2: Idempotent Database Updates

Running twice shouldn't create duplicates. Solution: upsert by Shopify order ID.

```php
// ShopifyVatInvoiceService.php
public function saveScraperResult(array $data): ShopifyVatInvoice
{
    $orderId = $data['shopify_order_id'];
    
    // Find existing or create new
    $invoice = $this->repository->findByShopifyOrderId($orderId) 
               ?? new ShopifyVatInvoice();
    
    $invoice->setShopifyOrderId($orderId);
    $invoice->setOrderName($data['order_name']);
    
    if ($data['success']) {
        $invoice->markAsDownloaded($data['filepath'], $data['invoice_number']);
    } else {
        $invoice->markAsFailed($data['error']);
    }
    
    $this->em->persist($invoice);
    $this->em->flush();
    return $invoice;
}
```

### Problem 3: Getting Order IDs from GraphQL

Shopify's `legacyResourceId` is needed for Admin URLs. The GraphQL query:

```graphql
query GetOrders($query: String!, $first: Int!) {
  orders(query: $query, first: $first) {
    edges {
      node {
        id
        legacyResourceId  # ← This is what you need: "12237732118863"
        name              # "#8512"
        createdAt
        totalPriceSet { shopMoney { amount currencyCode } }
      }
    }
  }
}
```

### Problem 4: CORS for Local Development

The scraper runs on `localhost:8000`, your app on a different port. The Python scraper includes permissive CORS:

```python
# Already included in this scraper
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Key Takeaways

1. **Don't trust `statusPageUrl`** — it expires and has view limits
2. **Use `legacyResourceId`** — it's the numeric ID for Admin URLs
3. **Handle `needs_login` gracefully** — pause UI, don't fail silently
4. **Upsert, don't insert** — makes re-running safe
5. **Keep browser window open** — session cookies persist

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `needs_login: true` | Log in via browser → call `/session/login-complete` |
| Login not persisting | Delete `.browser-profile/` and re-login |
| No invoice found | Order may not have VAT invoice yet—check in Shopify Admin |
| Errors | Check `screenshots/` for debug images |

## Disclaimer

**Not affiliated with Shopify Inc.** Shopify® is a registered trademark of Shopify Inc. Use at your own risk.

## License

MIT
