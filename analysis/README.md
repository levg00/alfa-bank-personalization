# Calculations

[↩ Back to the project](../README.md)

**Python · Pandas**

🗂️ [Data structure](../data/README.md)

<details>
<summary>Loading and preparing the tables</summary>

```python
from pathlib import Path
from statistics import NormalDist
import math
import pandas as pd

data_dir = Path("data")
csv_options = dict(sep=";", encoding="cp1251", decimal=",", low_memory=False)

profiles = pd.read_csv(data_dir / "Uid_data.csv", **csv_options)
payments = pd.read_csv(data_dir / "Uid_payment.csv", **csv_options)
links = pd.read_csv(data_dir / "Fid_Uid_link.csv", **csv_options)
products = pd.read_csv(data_dir / "Uid_product.csv", **csv_options)

# Use two-digit OKVED codes to compare industries
# Separate standalone entities from groups by the number of records sharing a GROUP_ID
profiles["sector"] = profiles["MAINOKVED_CODE"].astype("string").str.extract(r"^(\d{2})", expand=False)
profiles["in_group"] = profiles.groupby("GROUP_ID")["SYNTHETIC_U"].transform("size").gt(1)

corporate = profiles[profiles["REVENUE_COMPANY"] >= 500_000_000]
clients = corporate[corporate["CL_TYPE"] == "CLIENT"]
trading = clients[clients["sector"].isin(["46", "47"])]
wholesalers = clients[clients["sector"] == "46"]

# Exclude repeated IDs to avoid matching a payment to multiple profiles
ambiguous_ids = profiles.loc[profiles["SYNTHETIC_U"].duplicated(keep=False), "SYNTHETIC_U"].unique()
unique_profiles = profiles[~profiles["SYNTHETIC_U"].isin(ambiguous_ids)]
group_by_id = unique_profiles.set_index("SYNTHETIC_U")["GROUP_ID"]
sector_by_id = unique_profiles.set_index("SYNTHETIC_U")["sector"]

# Remove self-transfers and payments with non-positive amounts
clean_payments = payments[
    (payments["PAY_AMT"] > 0)
    & (payments["PAYER"] != payments["BENEFICIARY"])
    & ~payments["PAYER"].isin(ambiguous_ids)
    & ~payments["BENEFICIARY"].isin(ambiguous_ids)
].copy()
clean_payments["payer_group"] = clean_payments["PAYER"].map(group_by_id)
clean_payments["recipient_group"] = clean_payments["BENEFICIARY"].map(group_by_id)
clean_payments["intragroup"] = (
    clean_payments["payer_group"].notna()
    & clean_payments["payer_group"].eq(clean_payments["recipient_group"])
)
```

</details>

## Customer base and segments

| Metric | Result |
| :--- | :--- |
| Base with revenue of at least RUB 500 million | **65,540 records** |
| Current customers | **28,463**, including **10,147** trading customers |
| Wholesale trade | **27.44%** of the base |
| Companies in groups | **76.30%** of records in the base |
| Groups containing companies from different industries | **84.60%** of trading groups |
| Link to an individual | **36.07%** of records in the base |
| S1: standalone trading companies | **1,994** |
| S2: trading companies in groups | **8,153** legal entities in **5,921** groups; **80.35%** of trading customers |

<details>
<summary><b>How we calculated it</b></summary>

**Base with revenue of at least RUB 500 million**

Number of records with revenue of at least RUB 500 million.

```python
base_size = len(corporate)
```

**Current customers**

Number of CLIENT records in the selected base.

```python
client_count = len(clients)
```

**Trading customers**

Number of current customers with OKVED industry code 46 or 47.

```python
trade_count = len(trading)
```

**Wholesale trade**

Number of records with OKVED code 46 / number of records in the base × 100%.

```python
wholesale_share = corporate["sector"].eq("46").fillna(False).mean()
```

**Companies in groups**

Number of records whose GROUP_ID appears more than once / number of records in the base × 100%.

```python
group_share = corporate["in_group"].mean()
```

**Groups containing companies from different industries**

Number of trading groups containing more than one two-digit OKVED code / number of trading groups × 100%.

```python
trade_groups = trading.loc[trading["in_group"], "GROUP_ID"].unique()
members = profiles[profiles["GROUP_ID"].isin(trade_groups)]
sectors_per_group = members.groupby("GROUP_ID")["sector"].nunique()
mixed_group_share = sectors_per_group.gt(1).mean()
```

**Link to an individual**

Number of records in the base whose ID appears in the individual–company links table / number of records in the base × 100%.

```python
linked_record_share = corporate["SYNTHETIC_U"].isin(links["SYNTHETIC_U"]).mean()
```

**S1: standalone trading companies**

Number of trading customers that do not belong to a group.

```python
solo_count = (~trading["in_group"]).sum()
```

**S2: trading companies in groups**

group_entity_count is the number of trading customers in groups; trade_group_share is their share of all trading customers; trade_group_count is the number of unique groups.

```python
group_entity_count = trading["in_group"].sum()
trade_group_share = group_entity_count / len(trading)
trade_group_count = len(trade_groups)
```

</details>

## Basis for product selection

| Metric | Result |
| :--- | :--- |
| Receipt concentration | For **62.17%** of wholesalers with receipt data, the three largest payers account for more than **70%** of receipts |
| Factoring | **0.25%** of wholesalers have a factoring flag in their profile |
| Foreign trade | **46.73%** of wholesalers have a Federal Customs Service (FTS) flag; **93.87%** of these have no record of a foreign trade product |
| Intragroup payments | For **28.89%** of group customers with outgoing payments, more than **20%** of the amount goes to other group members |

<details>
<summary><b>How we calculated it</b></summary>

**Receipt concentration**

For each wholesaler, divide receipts from the three largest payers by all its receipts. Count the wholesalers for which this share exceeds 70% and divide that count by the number of wholesalers with receipt data. Multiply by 100%.

```python
incoming = (
    clean_payments[clean_payments["BENEFICIARY"].isin(clients["SYNTHETIC_U"])]
    .groupby(["BENEFICIARY", "PAYER"])["PAY_AMT"].sum()
)
top3 = incoming.sort_values(ascending=False).groupby(level="BENEFICIARY").head(3)
top3_share = (
    top3.groupby(level="BENEFICIARY").sum()
    / incoming.groupby(level="BENEFICIARY").sum()
)
wholesale_top3 = top3_share.reindex(wholesalers["SYNTHETIC_U"]).dropna()
concentrated_share = wholesale_top3.gt(0.70).mean()
```

**Factoring**

Number of wholesalers with FACTORING_MARK = 1 / number of wholesalers × 100%.

```python
factoring_share = wholesalers["FACTORING_MARK"].eq(1).mean()
```

**Foreign trade: FTS flag**

Number of wholesalers with FTS_FLAG = 1 / number of wholesalers × 100%.

```python
customs_clients = wholesalers[wholesalers["FTS_FLAG"] == 1]
foreign_trade_ids = products.loc[products["PRODUCT"] == "ВЭД", "SYNTHETIC_U"]
customs_share = len(customs_clients) / len(wholesalers)
```

**Foreign trade: no product record**

Number of wholesalers with an FTS flag and no record of a foreign trade product / number of wholesalers with an FTS flag × 100%.

```python
without_foreign_trade_share = (~customs_clients["SYNTHETIC_U"].isin(foreign_trade_ids)).mean()
```

**Intragroup payments**

For each customer, divide the amount paid to other members of its group by all its outgoing payments. Count the customers for which this share exceeds 20% and divide that count by the number of group customers with outgoing payment data. Multiply by 100%.

```python
outgoing = clean_payments[clean_payments["PAYER"].isin(clients["SYNTHETIC_U"])]
outgoing_total = outgoing.groupby("PAYER")["PAY_AMT"].sum()
intragroup_total = outgoing[outgoing["intragroup"]].groupby("PAYER")["PAY_AMT"].sum()
intragroup_share = intragroup_total.reindex(outgoing_total.index, fill_value=0) / outgoing_total

group_clients = clients.loc[clients["in_group"], "SYNTHETIC_U"]
group_payment_share = intragroup_share.reindex(group_clients).dropna()
active_intragroup_share = group_payment_share.gt(0.20).mean()
```

</details>

## Group structure and payment relationships

| Metric | Result |
| :--- | :--- |
| Leading industry | In **89.93%** of trading groups, one industry contributes at least half of known revenue |
| Largest payment recipient | For **71.28%** of customers, the recipient belongs to a different industry; only pairs with known industries on both sides are included |

<details>
<summary><b>How we calculated it</b></summary>

**Leading industry**

Within each trading group, sum known positive revenue by industry. Divide the revenue of the largest industry by the total. Calculate the share of groups for which the result is at least 50%.

```python
revenue_by_sector = (
    members[(members["REVENUE_COMPANY"] > 0) & members["sector"].notna()]
    .groupby(["GROUP_ID", "sector"])["REVENUE_COMPANY"].sum()
)
dominant_share = (
    revenue_by_sector.groupby(level="GROUP_ID").max()
    / revenue_by_sector.groupby(level="GROUP_ID").sum()
)
dominant_group_share = dominant_share.ge(0.50).mean()
```

**Largest payment recipient**

For each customer, select the recipient with the largest total payment amount. Number of customers whose industry differs from the recipient's / number of customers with known industries on both sides × 100%.

```python
largest = (
    outgoing.groupby(["PAYER", "BENEFICIARY"], as_index=False)["PAY_AMT"].sum()
    .sort_values(["PAY_AMT", "BENEFICIARY"], ascending=[False, True])
    .groupby("PAYER").head(1).copy()
)
largest["payer_sector"] = largest["PAYER"].map(sector_by_id)
largest["recipient_sector"] = largest["BENEFICIARY"].map(sector_by_id)
known = largest.dropna(subset=["payer_sector", "recipient_sector"])
different_sector_share = known["payer_sector"].ne(known["recipient_sector"]).mean()
```

</details>

## Pilot size and minimum detectable effect

| Metric | Result |
| :--- | :--- |
| Participants | **7,915** standalone companies and whole groups |
| Treatment / control / no messages | **3,561 / 3,561 / 793** |
| Minimum detectable effect (MDE) | **Around 20% relative uplift** with an assumed baseline conversion of **10%**, a significance level of **5%**, and power of **80%** |

<details>
<summary><b>How we calculated it</b></summary>

**Participants and allocation**

Participants = standalone trading companies + trading groups. Allocate 45% to treatment and 45% to control, rounding down; assign the remainder to the no-message arm.

```python
units = int(solo_count + trade_group_count)
test_size = int(units * 0.45)
control_size = int(units * 0.45)
no_messages_size = units - test_size - control_size
```

**Minimum detectable effect (MDE)**

Insert the treatment arm size, an assumed conversion of 10%, a significance level of 5%, and power of 80% into the MDE formula. Obtain the coefficients in Python using NormalDist.inv_cdf. Convert the result to a percentage. Rounding to the nearest whole percent gives around 20%.

```python
alpha = 0.05
power = 0.80
p0 = 0.10  # Pilot assumption; the data contains no application history

normal = NormalDist()
z_alpha = normal.inv_cdf(1 - alpha / 2)
z_power = normal.inv_cdf(power)
mde_relative = (z_alpha + z_power) / p0 * math.sqrt(2 * p0 * (1 - p0) / test_size)
```

</details>

## Individuals linked to multiple customers

| Metric | Result |
| :--- | :--- |
| Individuals linked to at least two companies | **10.01%** of individuals linked to current customers |

<details>
<summary><b>How we calculated it</b></summary>

**Individuals linked to at least two companies**

Number of individuals linked to at least two current customers / number of individuals linked to at least one current customer × 100%.

```python
client_links = links[links["SYNTHETIC_U"].isin(clients["SYNTHETIC_U"])]
companies_per_person = client_links.groupby("SYNTHETIC_F")["SYNTHETIC_U"].nunique()
multi_company_share = companies_per_person.ge(2).mean()
```

</details>
