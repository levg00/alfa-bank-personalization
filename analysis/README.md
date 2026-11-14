# Расчёты

[↩ К проекту](../README.ru.md)

**Python · Pandas**

🗂️ [Структура данных](../data/README.md)

<details>
<summary>Загрузка и подготовка таблиц</summary>

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

# Объединяем коды ОКВЭД до двух цифр для сравнения отраслей
# Одиночные юрлица отделяем от групп по числу записей с общим GROUP_ID
profiles["sector"] = profiles["MAINOKVED_CODE"].astype("string").str.extract(r"^(\d{2})", expand=False)
profiles["in_group"] = profiles.groupby("GROUP_ID")["SYNTHETIC_U"].transform("size").gt(1)

corporate = profiles[profiles["REVENUE_COMPANY"] >= 500_000_000]
clients = corporate[corporate["CL_TYPE"] == "CLIENT"]
trading = clients[clients["sector"].isin(["46", "47"])]
wholesalers = clients[clients["sector"] == "46"]

# Исключаем повторяющиеся ID, чтобы не привязать платёж к нескольким профилям
ambiguous_ids = profiles.loc[profiles["SYNTHETIC_U"].duplicated(keep=False), "SYNTHETIC_U"].unique()
unique_profiles = profiles[~profiles["SYNTHETIC_U"].isin(ambiguous_ids)]
group_by_id = unique_profiles.set_index("SYNTHETIC_U")["GROUP_ID"]
sector_by_id = unique_profiles.set_index("SYNTHETIC_U")["sector"]

# Убираем переводы самим себе и платежи с неположительной суммой
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

## Клиентская база и сегменты

| Показатель | Результат |
| :--- | :--- |
| База с выручкой от 500 млн ₽ | **65 540 записей** |
| Действующие клиенты | **28 463**, из них **10 147** торговых |
| Оптовая торговля | **27,44%** базы |
| Компании в группах | **76,30%** записей базы |
| Группы с компаниями разных отраслей | **84,60%** торговых групп |
| Связь с физлицом | **36,07%** записей базы |
| S1: самостоятельные торговые компании | **1 994** |
| S2: торговые компании в группах | **8 153** юрлица в **5 921** группе; **80,35%** торговых клиентов |

<details>
<summary><b>Как посчитали</b></summary>

**База с выручкой от 500 млн ₽**

Число записей с выручкой от 500 млн ₽.

```python
base_size = len(corporate)
```

**Действующие клиенты**

Число записей CLIENT в отобранной базе.

```python
client_count = len(clients)
```

**Торговые клиенты**

Число действующих клиентов с ОКВЭД 46 или 47.

```python
trade_count = len(trading)
```

**Оптовая торговля**

Число записей с ОКВЭД 46 / число записей в базе × 100%.

```python
wholesale_share = corporate["sector"].eq("46").fillna(False).mean()
```

**Компании в группах**

Число записей, у которых GROUP_ID встречается больше одного раза / число записей в базе × 100%.

```python
group_share = corporate["in_group"].mean()
```

**Группы с компаниями разных отраслей**

Число торговых групп, где встречается больше одного двухзначного кода ОКВЭД / число торговых групп × 100%.

```python
trade_groups = trading.loc[trading["in_group"], "GROUP_ID"].unique()
members = profiles[profiles["GROUP_ID"].isin(trade_groups)]
sectors_per_group = members.groupby("GROUP_ID")["sector"].nunique()
mixed_group_share = sectors_per_group.gt(1).mean()
```

**Связь с физлицом**

Число записей базы с ID в таблице связей с физлицами / число записей в базе × 100%.

```python
linked_record_share = corporate["SYNTHETIC_U"].isin(links["SYNTHETIC_U"]).mean()
```

**S1: самостоятельные торговые компании**

Число торговых клиентов, не входящих в группу.

```python
solo_count = (~trading["in_group"]).sum()
```

**S2: торговые компании в группах**

group_entity_count — число торговых клиентов в группах; trade_group_share — их доля среди торговых клиентов; trade_group_count — число уникальных групп.

```python
group_entity_count = trading["in_group"].sum()
trade_group_share = group_entity_count / len(trading)
trade_group_count = len(trade_groups)
```

</details>

## Основания для выбора продуктов

| Показатель | Результат |
| :--- | :--- |
| Концентрация поступлений | У **62,17%** оптовиков с данными о поступлениях три крупнейших плательщика дают более **70%** поступлений |
| Факторинг | У **0,25%** оптовиков есть флаг факторинга в профиле |
| Внешняя торговля | У **46,73%** оптовиков есть флаг ФТС; у **93,87%** из них нет записи о продукте ВЭД |
| Внутригрупповые платежи | У **28,89%** клиентов групп с исходящими платежами более **20%** суммы уходит другим участникам группы |

<details>
<summary><b>Как посчитали</b></summary>

**Концентрация поступлений**

Для каждого оптовика делим поступления от трёх крупнейших плательщиков на все его поступления. Считаем, у скольких оптовиков эта доля выше 70%, и делим их число на число оптовиков с данными о поступлениях. Умножаем на 100%.

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

**Факторинг**

Число оптовиков с FACTORING_MARK = 1 / число оптовиков × 100%.

```python
factoring_share = wholesalers["FACTORING_MARK"].eq(1).mean()
```

**Внешняя торговля: флаг ФТС**

Число оптовиков с FTS_FLAG = 1 / число оптовиков × 100%.

```python
customs_clients = wholesalers[wholesalers["FTS_FLAG"] == 1]
foreign_trade_ids = products.loc[products["PRODUCT"] == "ВЭД", "SYNTHETIC_U"]
customs_share = len(customs_clients) / len(wholesalers)
```

**Внешняя торговля: нет записи о ВЭД**

Число оптовиков с флагом ФТС, у которых нет записи о продукте ВЭД / число оптовиков с флагом ФТС × 100%.

```python
without_foreign_trade_share = (~customs_clients["SYNTHETIC_U"].isin(foreign_trade_ids)).mean()
```

**Внутригрупповые платежи**

Для каждого клиента делим сумму платежей другим участникам своей группы на все его исходящие платежи. Считаем, у скольких клиентов эта доля выше 20%, и делим их число на число клиентов групп с данными об исходящих платежах. Умножаем на 100%.

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

## Структура групп и платёжные связи

| Показатель | Результат |
| :--- | :--- |
| Ведущая отрасль | У **89,93%** торговых групп одна отрасль даёт не менее половины известной выручки |
| Крупнейший получатель платежей | У **71,28%** клиентов он относится к другой отрасли; учтены пары с известными отраслями обеих сторон |

<details>
<summary><b>Как посчитали</b></summary>

**Ведущая отрасль**

В каждой торговой группе складываем известную положительную выручку по отраслям. Делим выручку крупнейшей отрасли на общую. Считаем долю групп, где результат не ниже 50%.

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

**Крупнейший получатель платежей**

Для каждого клиента выбираем получателя с наибольшей суммой платежей. Число клиентов, чья отрасль отличается от отрасли получателя / число клиентов с известными отраслями обеих сторон × 100%.

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

## Размер пилота и минимальный эффект

| Показатель | Результат |
| :--- | :--- |
| Участники | **7 915** самостоятельных компаний и целых групп |
| Тест / контроль / без сообщений | **3 561 / 3 561 / 793** |
| Минимальный детектируемый эффект (MDE) | **Около 20% относительного роста** при сценарной базовой конверсии **10%**, значимости **5%** и мощности **80%** |

<details>
<summary><b>Как посчитали</b></summary>

**Участники и распределение**

Участники = самостоятельные торговые компании + торговые группы. В тест и контроль берём по 45% с округлением вниз; оставшихся относим в ветку без сообщений.

```python
units = int(solo_count + trade_group_count)
test_size = int(units * 0.45)
control_size = int(units * 0.45)
no_messages_size = units - test_size - control_size
```

**Минимальный детектируемый эффект (MDE)**

Подставляем размер тестовой ветки, сценарную конверсию 10%, значимость 5% и мощность 80% в формулу MDE. Коэффициенты получаем в Python через NormalDist.inv_cdf. Результат переводим в проценты. После округления до целого получаем около 20%.

```python
alpha = 0.05
power = 0.80
p0 = 0.10  # Допущение для пилота, в данных нет истории заявок

normal = NormalDist()
z_alpha = normal.inv_cdf(1 - alpha / 2)
z_power = normal.inv_cdf(power)
mde_relative = (z_alpha + z_power) / p0 * math.sqrt(2 * p0 * (1 - p0) / test_size)
```

</details>

## Связи физлиц с несколькими клиентами

| Показатель | Результат |
| :--- | :--- |
| Физлица, связанные минимум с двумя компаниями | **10,01%** среди физлиц, связанных с действующими клиентами |

<details>
<summary><b>Как посчитали</b></summary>

**Физлица, связанные минимум с двумя компаниями**

Число физлиц, связанных минимум с двумя действующими клиентами / число физлиц, связанных хотя бы с одним действующим клиентом × 100%.

```python
client_links = links[links["SYNTHETIC_U"].isin(clients["SYNTHETIC_U"])]
companies_per_person = client_links.groupby("SYNTHETIC_F")["SYNTHETIC_U"].nunique()
multi_company_share = companies_per_person.ge(2).mean()
```

</details>
