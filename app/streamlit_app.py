"""
Order Intelligence — Streamlit front end.

A single operator-facing app over the order database:
  • Overview   — the case study + headline KPIs
  • Analytics  — revenue, product mix, repeat-buyer and geographic breakdowns
  • Browse     — full-text search across every order field
  • Live Extract — upload a scanned order PDF and watch Claude extract it

Analytics read from the ChromaDB vector store (app/chroma_db), which is built
from data/orders.csv by scripts/build_db.py.
"""

import os
import sys
import tempfile

import pandas as pd
import plotly.express as px
import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Load the API key from the project-root .env so live extraction can find it.
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(HERE, "..", ".env"))

from branding import ORG_NAME, ORG_SHORT, TAGLINE, category_of  # noqa: E402
from database_manager import OrderDatabaseManager  # noqa: E402

# --- Palette ----------------------------------------------------------------
# Category hues are drawn from a CVD-validated categorical set (assigned in a
# fixed order, never cycled); "Assorted" is the neutral catch-all bucket.
INK = "#1f2a27"
PRIMARY = "#2f6b5e"
CATEGORY_COLORS = {
    "Gummies": "#008300",    # green
    "Caramels": "#eda100",   # amber
    "Chocolate": "#eb6834",  # orange
    "Sampler": "#2a78d6",    # blue
    "Assorted": "#9aa0a6",   # neutral
    "Other": "#c3c6c4",
}

st.set_page_config(page_title=f"{ORG_SHORT} · Order Intelligence", page_icon="🌿", layout="wide")

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1180px;}
      h1, h2, h3 {letter-spacing: -0.01em; color: #1f2a27;}

      /* Sidebar — readable nav */
      section[data-testid="stSidebar"] {border-right: 1px solid #e2e6e3;}
      section[data-testid="stSidebar"] div[role="radiogroup"] label {
        padding: 8px 12px; border-radius: 10px; margin: 1px 0;
        font-size: 0.98rem; transition: background .15s;
      }
      section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {background:#e2e8e4;}

      /* Metric cards */
      div[data-testid="stMetric"] {
        background: #ffffff; border: 1px solid #e6e9e7; border-radius: 14px;
        padding: 14px 18px; box-shadow: 0 1px 2px rgba(0,0,0,0.04);
      }
      div[data-testid="stMetricLabel"] p {
        color: #6b7570; font-size: 0.72rem;
        text-transform: uppercase; letter-spacing: 0.04em;
      }
      div[data-testid="stMetricValue"] {color: #1f2a27; font-weight: 700;}

      /* Hero */
      .hero {background: linear-gradient(135deg,#2f6b5e,#3d8574); color:#fff;
             padding: 26px 30px; border-radius: 18px; margin-bottom: 14px;}
      .hero h1 {color:#fff; margin:0 0 6px 0; font-size:1.9rem;}
      .hero p {color:#e9f2ee; margin:0; font-size:1.02rem;}
      .tag {display:inline-block; background:#eef3f0; color:#2f6b5e; font-weight:600;
            padding:3px 11px; border-radius:999px; font-size:.75rem; margin-right:6px;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_db():
    return OrderDatabaseManager(db_path=os.path.join(HERE, "chroma_db"))


@st.cache_data(show_spinner="Loading orders…")
def load_frame():
    """Load every record from the vector DB and clean it for analytics."""
    df = get_db().get_all_records()
    if df.empty:
        return df
    for col in ["Unit_Price", "Quantity", "Extended_Price", "Total_Amount", "Sub_Total"]:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["Date_parsed"] = pd.to_datetime(df.get("Date"), errors="coerce")
    df["Category"] = df["Product_Code"].map(category_of)
    return df


def order_level(df: pd.DataFrame) -> pd.DataFrame:
    """One row per unique order (dedupe line items) for revenue that doesn't
    double-count multi-item orders."""
    d = df[df["Order_Number"].astype(str).str.len() > 0].copy()
    return d.drop_duplicates(subset="Order_Number")


def money(x) -> str:
    try:
        return f"${x:,.0f}"
    except (TypeError, ValueError):
        return "—"


# ---------------------------------------------------------------------------
db = get_db()
df = load_frame()

st.sidebar.markdown(f"### 🌿 {ORG_SHORT}")
st.sidebar.caption(TAGLINE)
page = st.sidebar.radio(
    "Navigate",
    ["Overview", "Analytics", "Browse orders", "Live extraction", "About this demo"],
    label_visibility="collapsed",
)
st.sidebar.divider()
if not df.empty:
    st.sidebar.metric("Records in database", f"{len(df):,}")
st.sidebar.caption("Synthetic, anonymized demo data.")


def page_overview():
    st.markdown(
        f"""
        <div class="hero">
          <h1>Order Intelligence</h1>
          <p>Turning scanned paper order forms into a searchable, analyzable database — for {ORG_NAME}.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        "<span class='tag'>Claude Vision extraction</span>"
        "<span class='tag'>ChromaDB vector store</span>"
        "<span class='tag'>Streamlit ops UI</span>",
        unsafe_allow_html=True,
    )
    st.write("")

    if df.empty:
        st.warning("No data loaded. Run `python scripts/build_db.py` first.")
        return

    orders = order_level(df)
    revenue = orders["Total_Amount"].sum(skipna=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Orders processed", f"{orders['Order_Number'].nunique():,}")
    c2.metric("Line items", f"{len(df):,}")
    c3.metric("Unique members", f"{df['Customer_Name'].nunique():,}")
    c4.metric("Revenue represented", money(revenue))

    st.write("")
    left, right = st.columns([3, 2])
    with left:
        st.subheader("The problem")
        st.markdown(
            f"""
{ORG_SHORT} took orders on **paper forms**, scanned in bulk to PDF — hundreds of
low-quality Adobe Scans a week. Fulfilling and understanding the business meant
a person retyping every slip: customer, shipping address, products, totals.

**This system reads the scans automatically.** A hybrid text + vision pipeline
built on Claude extracts structured order data from each page, standardizes
messy product codes, stores everything in a searchable vector database, and
gives the owner a dashboard they actually use.
            """
        )
    with right:
        st.subheader("At a glance")
        cat = (
            df.groupby("Category")["Order_Number"].count().sort_values(ascending=False)
        )
        fig = px.bar(
            cat, orientation="h", color=cat.index,
            color_discrete_map=CATEGORY_COLORS,
        )
        fig.update_layout(
            showlegend=False, height=260, margin=dict(l=0, r=0, t=0, b=0),
            xaxis_title=None, yaxis_title=None, plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)


def page_analytics():
    st.header("Analytics")
    if df.empty:
        st.warning("No data loaded.")
        return

    orders = order_level(df)

    # Revenue over time
    ts = orders.dropna(subset=["Date_parsed"]).copy()
    if not ts.empty:
        ts["Month"] = ts["Date_parsed"].dt.to_period("M").dt.to_timestamp()
        monthly = ts.groupby("Month")["Total_Amount"].sum().reset_index()
        st.subheader("Revenue by month")
        fig = px.area(monthly, x="Month", y="Total_Amount")
        fig.update_traces(line_color=PRIMARY, fillcolor="rgba(47,107,94,0.15)")
        fig.update_layout(height=300, margin=dict(l=0, r=0, t=8, b=0),
                          yaxis_title="Revenue ($)", xaxis_title=None,
                          plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Product mix (by line items)")
        mix = df.groupby("Category")["Order_Number"].count().reset_index()
        fig = px.pie(mix, names="Category", values="Order_Number", hole=0.55,
                     color="Category", color_discrete_map=CATEGORY_COLORS)
        fig.update_layout(height=320, margin=dict(l=0, r=0, t=8, b=0),
                          legend=dict(orientation="h", y=-0.1))
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.subheader("Top products")
        top = (df.groupby(["Product_Code", "Product_Description"])
                 .size().reset_index(name="Line items")
                 .sort_values("Line items", ascending=False).head(8))
        top["Category"] = top["Product_Code"].map(category_of)
        fig = px.bar(top, x="Line items", y="Product_Description", orientation="h",
                     color="Category", color_discrete_map=CATEGORY_COLORS)
        fig.update_layout(height=320, margin=dict(l=0, r=0, t=8, b=0),
                          yaxis_title=None, xaxis_title=None,
                          yaxis=dict(autorange="reversed"),
                          plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)

    # Repeat buyers
    st.subheader("Members & loyalty")
    # Derive per-customer stats from order-level rows so spend isn't inflated
    # by multi-item orders.
    per_customer = (
        orders.groupby("Customer_Name")
              .agg(orders=("Order_Number", "nunique"), spent=("Total_Amount", "sum"))
              .reset_index()
    )
    per_customer["Type"] = per_customer["orders"].apply(
        lambda n: "One-time" if n == 1 else "Repeat (2-3)" if n <= 3 else "Loyal (4-6)" if n <= 6 else "VIP (7+)"
    )
    repeat_rate = (per_customer["orders"] > 1).mean() * 100
    m1, m2, m3 = st.columns(3)
    m1.metric("Repeat-buyer rate", f"{repeat_rate:.0f}%")
    m2.metric("Avg orders / member", f"{per_customer['orders'].mean():.1f}")
    m3.metric("Members with 4+ orders", f"{(per_customer['orders'] >= 4).sum():,}")
    seg = per_customer["Type"].value_counts().reindex(
        ["One-time", "Repeat (2-3)", "Loyal (4-6)", "VIP (7+)"]).fillna(0).reset_index()
    seg.columns = ["Segment", "Members"]
    fig = px.bar(seg, x="Segment", y="Members", color="Segment",
                 color_discrete_sequence=["#c9cccf", "#9fbf8f", "#6a8d3f", PRIMARY])
    fig.update_layout(height=280, showlegend=False, margin=dict(l=0, r=0, t=8, b=0),
                      xaxis_title=None, yaxis_title=None, plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)

    # Geography
    st.subheader("Where orders ship")
    geo = orders.groupby("Shipping_State").size().reset_index(name="Orders")
    geo = geo[geo["Shipping_State"].str.len() == 2]
    fig = px.choropleth(geo, locations="Shipping_State", locationmode="USA-states",
                        color="Orders", scope="usa",
                        color_continuous_scale=["#e7efec", "#6a8d3f", PRIMARY])
    fig.update_layout(height=380, margin=dict(l=0, r=0, t=0, b=0))
    st.plotly_chart(fig, use_container_width=True)


def page_browse():
    st.header("Browse orders")
    q = st.text_input("🔍 Search", placeholder="Customer name, order #, product, city, state…")
    result = db.search_records(q) if q else df
    st.caption(f"{len(result):,} matching line items")
    show_cols = ["Order_Number", "Date", "Customer_Name", "Shipping_City",
                 "Shipping_State", "Product_Code", "Product_Description",
                 "Quantity", "Total_Amount"]
    show_cols = [c for c in show_cols if c in result.columns]
    st.dataframe(result[show_cols], width="stretch", height=520)


def page_live():
    st.header("Live extraction")
    st.markdown(
        "Upload a scanned order form (PDF). Claude reads the page with a hybrid "
        "text + vision pipeline and returns structured order data — the same "
        "engine that built this database."
    )
    sample = os.path.join(HERE, "..", "samples", "sample_order_form.pdf")
    if os.path.exists(sample):
        with open(sample, "rb") as f:
            st.download_button("⬇️ Download a synthetic sample form to try",
                               f.read(), file_name="sample_order_form.pdf",
                               mime="application/pdf")
    if not os.getenv("ANTHROPIC_API_KEY"):
        st.info(
            "No `ANTHROPIC_API_KEY` detected. Add it to a `.env` file in the project "
            "root and restart the app to run extraction. You can still upload a file "
            "and explore the other tabs."
        )
    up = st.file_uploader("Order form PDF", type=["pdf"])
    if not up:
        return

    import pypdfium2 as pdfium

    # Write once, read the page count so the range control reflects the real file.
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(up.getvalue())
        path = tmp.name
    try:
        try:
            doc = pdfium.PdfDocument(path)
            n_pages = len(doc)
            doc.close()
        except Exception as e:
            st.error(f"Couldn't read that PDF: {e}")
            return

        st.caption(f"📄 **{up.name}** — {n_pages} page{'s' if n_pages != 1 else ''}")
        c1, c2 = st.columns(2)
        start = int(c1.number_input("First page", min_value=1, max_value=n_pages, value=1))
        end = int(c2.number_input("Last page", min_value=start, max_value=n_pages, value=n_pages))
        count = end - start + 1
        st.caption(f"Claude reads each page (one or two calls per page). Selected: {count} page{'s' if count != 1 else ''}.")

        if not st.button(f"🚀 Extract {count} page{'s' if count != 1 else ''} with Claude", type="primary"):
            return
        if not os.getenv("ANTHROPIC_API_KEY"):
            st.error(
                "No ANTHROPIC_API_KEY found. Add it to `.env` in the project root, "
                "then restart the app (Ctrl+C and `make run`)."
            )
            return

        from extraction import HybridPackingSlipExtractor
        extractor = HybridPackingSlipExtractor()

        progress = st.progress(0.0)
        status = st.empty()
        table = st.empty()
        records = []
        failures = 0
        for i, p in enumerate(range(start - 1, end)):
            status.write(f"Reading page {p + 1} of {end}…")
            try:
                records.extend(extractor.extract_page_data(path, p, up.name) or [])
            except Exception as e:  # one bad page shouldn't kill the run
                failures += 1
                st.warning(f"Page {p + 1} failed: {e}")
            progress.progress((i + 1) / count)
            if records:
                table.dataframe(pd.DataFrame(records), width="stretch")

        note = f" ({failures} page{'s' if failures != 1 else ''} failed)" if failures else ""
        if records:
            status.success(f"Extracted {len(records)} line item(s) from {count} page{'s' if count != 1 else ''}{note}.")
        else:
            status.info(f"No structured order data found in pages {start}–{end}{note}.")
    finally:
        os.unlink(path)


def page_about():
    st.header("About this demo")
    st.markdown(
        f"""
This is a portfolio case study, built from a real engagement and adapted for
public sharing.

**What it demonstrates**
- Taking an ambiguous, messy customer problem (hundreds of low-quality scanned
  paper order forms) and shipping a working AI system end to end.
- A hybrid **text + Claude Vision** extraction pipeline that reads garbage-quality
  Adobe scans into structured order records, with a second-pass vision check on
  names and addresses.
- **Data engineering**: standardizing 240+ OCR product-code variants down to a
  clean catalog, deduplicating orders, and loading into a **ChromaDB** vector
  store for full-text and semantic search.
- An operator-facing **Streamlit** app the business owner actually uses.

**Responsible data handling**
- All customer data here is **synthetic**: names, emails, and street addresses are
  replaced with non-reversible fakes (no `fake = f(real_name)` function exists),
  ZIPs are truncated to 3-digit prefixes, and each real customer maps to exactly
  one fake identity so repeat-buyer analytics stay intact.
- The organization and product names are genericized so nothing ties this public
  demo to the real client.

*Organization name, product catalog, and all identities on this page are
fictional.*
        """
    )


PAGES = {
    "Overview": page_overview,
    "Analytics": page_analytics,
    "Browse orders": page_browse,
    "Live extraction": page_live,
    "About this demo": page_about,
}
PAGES[page]()
