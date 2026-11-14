# Расчёты

**Python · Pandas · NumPy**

Запросы к данным кейса и результаты, использованные в решении.

<details>
<summary><b>Загрузка и подготовка таблиц</b></summary>

```python
from pathlib import Path
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

**80,35% торговых клиентов входят в группы компаний.**

| Показатель | Результат |
| :--- | ---: |
| Торговые клиенты | **10 147** |
| Самостоятельные торговые компании | **1 994** |
| Торговые юрлица в группах | **8 153** |
| Группы с торговыми клиентами | **5 921** |
| Все действующие клиенты с выручкой от 500 млн ₽ | **28 463** |
| Действующие клиенты в группах | **82,80%** |
| Записи среднего и крупного бизнеса в группах | **76,30%** |
| Оптовая торговля среди записей среднего и крупного бизнеса | **27,44%** |

Выделяем торговых клиентов и разделяем их на самостоятельные компании и участников групп.

<details>
<summary><b>Запрос на Pandas</b></summary>

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

</details>

## 2. Связи компаний с физлицами

**71,35% действующих клиентов связаны хотя бы с одним физлицом.**

| Показатель | Результат |
| :--- | ---: |
| Торговые клиенты со связью с физлицом | **73,67%** |
| Записи среднего и крупного бизнеса со связью с физлицом | **36,07%** |
| Люди, связанные минимум с двумя действующими клиентами | **10,01%** |

Считаем компании со связанным физлицом и людей, связанных с несколькими клиентами.

<details>
<summary><b>Запрос на Pandas</b></summary>

```python
linked_company_ids = links["SYNTHETIC_U"]
client_links = links[links["SYNTHETIC_U"].isin(clients["SYNTHETIC_U"])]
companies_per_person = client_links.groupby("SYNTHETIC_F")["SYNTHETIC_U"].nunique()

print(f"Действующие клиенты со связью: {clients['SYNTHETIC_U'].isin(linked_company_ids).mean():.2%}")
print(f"Торговые клиенты со связью: {trading['SYNTHETIC_U'].isin(linked_company_ids).mean():.2%}")
print(f"Записи среднего и крупного бизнеса со связью: {corporate['SYNTHETIC_U'].isin(linked_company_ids).mean():.2%}")
print(f"Люди, связанные минимум с двумя клиентами: {companies_per_person.ge(2).mean():.2%}")
```

</details>

## 3. Зависимость от крупнейших покупателей

**У 62,17% оптовиков с данными о поступлениях более 70% поступлений приходится на трёх крупнейших плательщиков.**

| Показатель | Результат |
| :--- | ---: |
| Оптовики с данными о поступлениях | **91,46%** |
| Доля оптовиков с концентрацией выше 70% после исключения внутригрупповых переводов | **61,21%** |

Суммируем поступления от каждого плательщика. Считаем долю трёх крупнейших плательщиков в поступлениях каждого оптовика.

<details>
<summary><b>Запрос на Pandas</b></summary>

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

</details>

## 4. Внешняя торговля и банковские продукты

**У 93,87% оптовиков с флагом ФТС нет записи о продукте ВЭД в таблице продуктов.**

| Показатель | Результат |
| :--- | ---: |
| Оптовики с флагом ФТС | **46,73%** |
| Оптовики с флагом факторинга в профиле | **0,25%** |
| Оптовики с записью факторинга в таблице продуктов | **0,44%** |

Проверяем флаг ФТС, наличие ВЭД и факторинга у оптовых клиентов.

<details>
<summary><b>Запрос на Pandas</b></summary>

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

</details>

## 5. Платежи внутри группы

**У 28,89% клиентов групп с данными об исходящих платежах более 20% этих платежей идут другим участникам группы.**

| Показатель | Результат |
| :--- | ---: |
| Клиенты групп с данными об исходящих платежах | **22 868** |
| Из них с внутригрупповой долей выше 20% | **6 607** |

Для каждого клиента группы делим сумму переводов другим участникам группы на все его исходящие платежи.

<details>
<summary><b>Запрос на Pandas</b></summary>

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

</details>

## 6. Отраслевой состав групп

**У 89,93% торговых групп одна отрасль даёт не менее половины известной выручки.**

| Показатель | Результат |
| :--- | ---: |
| Группы с несколькими отраслями | **84,60%** |
| Группы с ведущей отраслью при полной выручке участников | **90,41%** |

Берём всех участников групп с торговыми клиентами. Для каждой группы считаем число отраслей и долю крупнейшей отрасли в известной выручке.

<details>
<summary><b>Запрос на Pandas</b></summary>

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

</details>

## 7. Отрасль крупнейшего получателя платежей

**У 71,28% клиентов с известными отраслями обеих сторон крупнейший получатель платежей относится к другой отрасли.**

Находим крупнейшего получателя по сумме исходящих платежей и сравниваем его отрасль с отраслью отправителя.

<details>
<summary><b>Запрос на Pandas</b></summary>

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

</details>

## 8. Распределение участников пилота

**7 915 единиц распределения: самостоятельные компании и целые группы.**

| Показатель | Результат |
| :--- | ---: |
| Тест | **3 561** |
| Контроль | **3 561** |
| Без сообщений | **793** |

Единица распределения: самостоятельная компания или целая группа. Выделяем 45% в тест, 45% в контроль, остаток в ветку без сообщений.

<details>
<summary><b>Запрос на Pandas</b></summary>

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

</details>
