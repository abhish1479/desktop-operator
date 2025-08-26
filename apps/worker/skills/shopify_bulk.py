import csv, os, requests

def row_to_product(row: dict) -> dict:
    title = row.get("Title") or row.get("title") or "Untitled"
    handle = row.get("Handle") or row.get("handle") or title.lower().replace(" ","-")
    body_html = row.get("Body") or ""
    price = row.get("Price") or "0.00"
    sku = row.get("SKU") or ""
    return {
        "title": title,
        "body_html": body_html,
        "handle": handle,
        "variants": [{"price": price, "sku": sku}],
        "status": "active"
    }

def product_by_handle(session, base, handle: str):
    r = session.get(f"{base}/products.json?handle={handle}")
    if r.ok:
        arr = r.json().get("products", [])
        return arr[0] if arr else None
    return None

def run(csv_path: str, update: bool = True) -> dict:
    base = f"https://{os.environ.get('SHOPIFY_STORE_DOMAIN')}/admin/api/2024-07"
    token = os.environ.get("SHOPIFY_ACCESS_TOKEN")
    if not token:
        return {"ok": False, "error": "missing SHOPIFY_ACCESS_TOKEN"}
    s = requests.Session()
    s.headers["X-Shopify-Access-Token"] = token

    created, updated, errs = [], [], []
    with open(csv_path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            product = row_to_product(row)
            try:
                existing = product_by_handle(s, base, product["handle"])
                if existing and update:
                    pid = existing["id"]
                    r = s.put(f"{base}/products/{pid}.json", json={"product": {**product, "id": pid}})
                    (updated if r.ok else errs).append(product["handle"])
                else:
                    r = s.post(f"{base}/products.json", json={"product": product})
                    (created if r.ok else errs).append(product["handle"])
            except Exception as e:
                errs.append(f"{product['handle']}: {e}")
    return {"ok": len(errs)==0, "created": created, "updated": updated, "errors": errs}
