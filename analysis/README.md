# Расчёты

**Python · Pandas · NumPy**

Запросы к данным кейса и результаты, использованные в решении.

<details>
<summary><b>Загрузка и подготовка таблиц</b></summary>

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

# Отрасль: первые две цифры ОКВЭД. Группа: больше одного юрлица.
profiles["sector"] = profiles["MAINOKVED_CODE"].astype("string").str.extract(r"^(\d{2})", expand=False)
profiles["in_group"] = profiles.groupby("GROUP_ID")["SYNTHETIC_U"].transform("size").gt(1)

corporate = profiles[profiles["REVENUE_COMPANY"] >= 500_000_000]
clients = corporate[corporate["CL_TYPE"] == "CLIENT"]
trading = clients[clients["sector"].isin(["46", "47"])]
wholesalers = clients[clients["sector"] == "46"]

# Для соединения платежей берём ID с единственным профилем.
ambiguous_ids = profiles.loc[profiles["SYNTHETIC_U"].duplicated(keep=False), "SYNTHETIC_U"].unique()
unique_profiles = profiles[~profiles["SYNTHETIC_U"].isin(ambiguous_ids)]
group_by_id = unique_profiles.set_index("SYNTHETIC_U")["GROUP_ID"]
sector_by_id = unique_profiles.set_index("SYNTHETIC_U")["sector"]

# Положительные платежи между разными компаниями с однозначными ID.
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

## 1. Клиентские сегменты

Выделяем торговых клиентов и разделяем их на самостоятельные компании и участников групп.

```python
trade_groups = trading.loc[trading["in_group"], "GROUP_ID"].unique()

print("Клиентов с выручкой от 500 млн ₽:", len(clients))
print("Торговых клиентов:", len(trading))
print("Самостоятельных торговых компаний:", (~trading["in_group"]).sum())
print("Торговых юрлиц в группах:", trading["in_group"].sum())
print("Групп с торговыми клиентами:", len(trade_groups))
print(f"Торговых клиентов в группах: {trading['in_group'].mean():.2%}")
print(f"Всех действующих клиентов в группах: {clients['in_group'].mean():.2%}")
print(f"Записей среднего и крупного бизнеса в группах: {corporate['in_group'].mean():.2%}")
print(f"Оптовая торговля среди записей среднего и крупного бизнеса: {corporate['sector'].eq('46').fillna(False).mean():.2%}")
```

**Результат:**

```text
Клиентов с выручкой от 500 млн ₽: 28463
Торговых клиентов: 10147
Самостоятельных торговых компаний: 1994
Торговых юрлиц в группах: 8153
Групп с торговыми клиентами: 5921
Торговых клиентов в группах: 80.35%
Всех действующих клиентов в группах: 82.80%
Записей среднего и крупного бизнеса в группах: 76.30%
Оптовая торговля среди записей среднего и крупного бизнеса: 27.44%
```

## 2. Зависимость от крупнейших покупателей

Суммируем поступления от каждого плательщика. Считаем долю трёх крупнейших плательщиков в поступлениях каждого оптовика.

```python
incoming = (
    clean_payments[clean_payments["BENEFICIARY"].isin(clients["SYNTHETIC_U"])]
    .groupby(["BENEFICIARY", "PAYER"])["PAY_AMT"].sum()
)
incoming_total = incoming.groupby(level="BENEFICIARY").sum()
top3 = incoming.sort_values(ascending=False).groupby(level="BENEFICIARY").head(3)
top3_share = top3.groupby(level="BENEFICIARY").sum() / incoming_total
wholesale_top3 = top3_share.reindex(wholesalers["SYNTHETIC_U"]).dropna()

# Отдельно считаем концентрацию после исключения внутригрупповых переводов.
external = clean_payments[
    ~clean_payments["intragroup"]
    & clean_payments["BENEFICIARY"].isin(clients["SYNTHETIC_U"])
].groupby(["BENEFICIARY", "PAYER"])["PAY_AMT"].sum()
external_share = (
    external.sort_values(ascending=False).groupby(level="BENEFICIARY").head(3).groupby(level="BENEFICIARY").sum()
    / external.groupby(level="BENEFICIARY").sum()
)
wholesale_external = external_share.reindex(wholesalers["SYNTHETIC_U"]).dropna()

print(f"Оптовики с долей топ-3 выше 70%: {wholesale_top3.gt(0.70).mean():.2%}")
print(f"Оптовики с данными о поступлениях: {len(wholesale_top3) / len(wholesalers):.2%}")
print(f"Доля топ-3 выше 70% без внутригрупповых переводов: {wholesale_external.gt(0.70).mean():.2%}")
```

**Результат:**

```text
Оптовики с долей топ-3 выше 70%: 62.17%
Оптовики с данными о поступлениях: 91.46%
Доля топ-3 выше 70% без внутригрупповых переводов: 61.21%
```

## 3. Платежи внутри группы

Для каждого клиента группы делим сумму переводов другим участникам группы на все его исходящие платежи.

```python
outgoing = clean_payments[clean_payments["PAYER"].isin(clients["SYNTHETIC_U"])]
outgoing_total = outgoing.groupby("PAYER")["PAY_AMT"].sum()
intragroup_total = outgoing[outgoing["intragroup"]].groupby("PAYER")["PAY_AMT"].sum()
intragroup_share = intragroup_total.reindex(outgoing_total.index, fill_value=0) / outgoing_total

group_clients = clients.loc[clients["in_group"], "SYNTHETIC_U"]
group_payment_share = intragroup_share.reindex(group_clients).dropna()

print("Компаний групп с данными об исходящих платежах:", len(group_payment_share))
print("Из них с внутригрупповой долей выше 20%:", group_payment_share.gt(0.20).sum())
print(f"Доля таких компаний: {group_payment_share.gt(0.20).mean():.2%}")
```

**Результат:**

```text
Компаний групп с данными об исходящих платежах: 22868
Из них с внутригрупповой долей выше 20%: 6607
Доля таких компаний: 28.89%
```

## 4. Внешняя торговля и банковские продукты

Проверяем флаг ФТС, наличие ВЭД и факторинга у оптовых клиентов.

```python
customs_clients = wholesalers[wholesalers["FTS_FLAG"] == 1]
foreign_trade_ids = products.loc[products["PRODUCT"] == "ВЭД", "SYNTHETIC_U"]
factoring_ids = products.loc[products["PRODUCT"] == "ФАКТОРИНГ", "SYNTHETIC_U"]
without_foreign_trade = ~customs_clients["SYNTHETIC_U"].isin(foreign_trade_ids)

print(f"Оптовики с флагом ФТС: {len(customs_clients) / len(wholesalers):.2%}")
print(f"Среди них без продукта ВЭД: {without_foreign_trade.mean():.2%}")
print(f"Оптовики с флагом факторинга в профиле: {wholesalers['FACTORING_MARK'].eq(1).mean():.2%}")
print(f"Оптовики с записью факторинга в таблице продуктов: {wholesalers['SYNTHETIC_U'].isin(factoring_ids).mean():.2%}")
```

**Результат:**

```text
Оптовики с флагом ФТС: 46.73%
Среди них без продукта ВЭД: 93.87%
Оптовики с флагом факторинга в профиле: 0.25%
Оптовики с записью факторинга в таблице продуктов: 0.44%
```

## 5. Отраслевой состав групп

Берём всех участников групп с торговыми клиентами. Для каждой группы считаем число отраслей и долю крупнейшей отрасли в известной выручке.

```python
members = profiles[profiles["GROUP_ID"].isin(trade_groups)]
sector_count = members.groupby("GROUP_ID")["sector"].nunique()
revenue_by_sector = (
    members[(members["REVENUE_COMPANY"] > 0) & members["sector"].notna()]
    .groupby(["GROUP_ID", "sector"])["REVENUE_COMPANY"].sum()
)
dominant_share = (
    revenue_by_sector.groupby(level="GROUP_ID").max()
    / revenue_by_sector.groupby(level="GROUP_ID").sum()
)

# Та же проверка для групп, где у каждого участника известна положительная выручка.
complete_revenue = members.groupby("GROUP_ID")["REVENUE_COMPANY"].apply(lambda s: s.gt(0).all())
complete_dominant = dominant_share.reindex(complete_revenue[complete_revenue].index).dropna()

print(f"Группы с несколькими отраслями: {sector_count.gt(1).mean():.2%}")
print(f"Группы с ведущей отраслью (доля ≥50%): {dominant_share.ge(0.50).mean():.2%}")
print(f"При полной выручке участников: {complete_dominant.ge(0.50).mean():.2%}")
```

**Результат:**

```text
Группы с несколькими отраслями: 84.60%
Группы с ведущей отраслью (доля ≥50%): 89.93%
При полной выручке участников: 90.41%
```

## 6. Связи компаний с физлицами

Считаем компании со связанным физлицом и людей, связанных с несколькими клиентами.

```python
linked_company_ids = links["SYNTHETIC_U"]
client_links = links[links["SYNTHETIC_U"].isin(clients["SYNTHETIC_U"])]
companies_per_person = client_links.groupby("SYNTHETIC_F")["SYNTHETIC_U"].nunique()

print(f"Действующие клиенты со связью: {clients['SYNTHETIC_U'].isin(linked_company_ids).mean():.2%}")
print(f"Торговые клиенты со связью: {trading['SYNTHETIC_U'].isin(linked_company_ids).mean():.2%}")
print(f"Записи среднего и крупного бизнеса со связью: {corporate['SYNTHETIC_U'].isin(linked_company_ids).mean():.2%}")
print(f"Люди, связанные минимум с двумя клиентами: {companies_per_person.ge(2).mean():.2%}")
```

**Результат:**

```text
Действующие клиенты со связью: 71.35%
Торговые клиенты со связью: 73.67%
Записи среднего и крупного бизнеса со связью: 36.07%
Люди, связанные минимум с двумя клиентами: 10.01%
```

## 7. Отрасль крупнейшего получателя платежей

Находим крупнейшего получателя по сумме исходящих платежей и сравниваем его отрасль с отраслью отправителя.

```python
largest_recipient = (
    outgoing.groupby(["PAYER", "BENEFICIARY"], as_index=False)["PAY_AMT"].sum()
    .sort_values(["PAY_AMT", "BENEFICIARY"], ascending=[False, True])
    .groupby("PAYER").head(1).copy()
)
largest_recipient["payer_sector"] = largest_recipient["PAYER"].map(sector_by_id)
largest_recipient["recipient_sector"] = largest_recipient["BENEFICIARY"].map(sector_by_id)
known_sectors = largest_recipient.dropna(subset=["payer_sector", "recipient_sector"])
different_sector = known_sectors["payer_sector"] != known_sectors["recipient_sector"]

print(f"Крупнейший получатель из другой отрасли: {different_sector.mean():.2%}")
```

**Результат:**

```text
Крупнейший получатель из другой отрасли: 71.28%
```

## 8. Распределение участников пилота

Единица распределения: самостоятельная компания или целая группа. Выделяем 45% в тест, 45% в контроль, остаток в ветку без сообщений.

```python
units = int((~trading["in_group"]).sum() + len(trade_groups))
test_size = int(units * 0.45)
control_size = int(units * 0.45)
no_messages_size = units - test_size - control_size

print("Всего участников:", units)
print("Тест:", test_size)
print("Контроль:", control_size)
print("Без сообщений:", no_messages_size)
```

**Результат:**

```text
Всего участников: 7915
Тест: 3561
Контроль: 3561
Без сообщений: 793
```

## 9. Коэффициенты и размер выборки

Для сценария роста конверсии с 10% до 12% рассчитываем размер одной ветки при значимости 5% и мощности 80%.

```python
alpha = 0.05
power = 0.80
p0, p1 = 0.10, 0.12

normal = NormalDist()
z_alpha = normal.inv_cdf(1 - alpha / 2)
z_power = normal.inv_cdf(power)
p_avg = (p0 + p1) / 2

required_per_arm = math.ceil(
    (z_alpha * math.sqrt(2 * p_avg * (1 - p_avg))
     + z_power * math.sqrt(p0 * (1 - p0) + p1 * (1 - p1))) ** 2
    / (p1 - p0) ** 2
)

print(f"z₁₋α/₂ = {z_alpha:.5f}")
print(f"z₁₋β = {z_power:.5f}")
print("Нужно участников на одну ветку:", required_per_arm)
```

**Результат:**

```text
z₁₋α/₂ = 1.95996
z₁₋β = 0.84162
Нужно участников на одну ветку: 3841
```

## 10. MDE по формуле из решения

Подставляем коэффициенты, базовую конверсию 10% и размер тестовой ветки в формулу из README проекта.

```python
mde_relative = (
    (z_alpha + z_power) / p0
    * math.sqrt(2 * p0 * (1 - p0) / test_size)
)

print(f"MDE с округлением до целого процента: {mde_relative:.0%}")
```

**Результат:**

```text
MDE с округлением до целого процента: 20%
```

[Полный код запросов](queries.py)
