"""Reproduce the case-school analysis without modifying the four source CSVs.
Python 3.10+, pandas, numpy. Example:
python recalculate.py --data-dir '/path/to/data (1)' --out-dir '../02_Расчёты'
"""
from pathlib import Path
from statistics import NormalDist
import argparse, hashlib, json, math
import numpy as np
import pandas as pd

ap=argparse.ArgumentParser()
ap.add_argument('--data-dir',required=True);ap.add_argument('--out-dir',required=True)
args=ap.parse_args();src=Path(args.data_dir);out=Path(args.out_dir);out.mkdir(parents=True,exist_ok=True)
names=['Uid_data.csv','Uid_payment.csv','Fid_Uid_link.csv','Uid_product.csv']
frames=[pd.read_csv(src/n,sep=';',encoding='cp1251',decimal=',',low_memory=False) for n in names]
u,p,l,pr=frames
manifest=[{'file':n,'rows':len(d),'columns':list(d.columns),'sha256':hashlib.sha256((src/n).read_bytes()).hexdigest()} for n,d in zip(names,frames)]
counts=u.SYNTHETIC_U.value_counts();ambiguous=set(counts[counts>1].index)
u['sector']=u.MAINOKVED_CODE.astype('string').str.extract(r'^(\d{2})',expand=False)
v=u[~u.SYNTHETIC_U.isin(ambiguous)].copy()
assert not v.SYNTHETIC_U.duplicated().any()
group_size=u.groupby('GROUP_ID').size()
u['group_records']=u.GROUP_ID.map(group_size)
s=u[u.REVENUE_COMPANY.ge(500_000_000)].copy()
c=s[s.CL_TYPE.eq('CLIENT')].copy();assert c.SYNTHETIC_U.is_unique
t=c[c.sector.isin(['46','47'])].copy();o=c[c.sector.eq('46')].copy()
for x in [s,c,t,o]:x['ingroup']=x.group_records.gt(1)
groupmap=v.set_index('SYNTHETIC_U').GROUP_ID;sectormap=v.set_index('SYNTHETIC_U').sector
metric=[]
def add(key,label,num,den,scope,source,method,kind='share'):
    val=float(num/den) if den else None
    metric.append(dict(id=key,metric=label,numerator=int(num),denominator=int(den),value=val,scope=scope,source=source,method=method,kind=kind))
add('wholesale_records','Опт среди записей СКБ',s.sector.eq('46').sum(),len(s),'Все записи с выручкой ≥ 500 млн','Uid_data: REVENUE_COMPANY, MAINOKVED_CODE','Код начинается с 46; знаменатель включает записи с неоднозначным ID')
add('client_group','Действующие клиенты СКБ в группах',c.ingroup.sum(),len(c),'CLIENT, выручка ≥ 500 млн','Uid_data: GROUP_ID','Состав группы определён по всем записям профиля; группа содержит > 1 записи')
add('all_group_records','Записи СКБ в группах',s.ingroup.sum(),len(s),'Все записи СКБ','Uid_data: GROUP_ID','Доля записей, принадлежащих группам с > 1 записи во всей базе')
add('trade_group','Торговые клиенты в группах',t.ingroup.sum(),len(t),'CLIENT, СКБ, ОКВЭД 46/47','Uid_data: CL_TYPE, GROUP_ID, MAINOKVED_CODE','Отбор торговых клиентов; состав группы по полной базе')
add('person_client','Клиенты СКБ со связью с физлицом',c.SYNTHETIC_U.isin(l.SYNTHETIC_U).sum(),len(c),'Действующие клиенты СКБ','Fid_Uid_link + Uid_data','Существует хотя бы одна связь; наличие или качество роли не измеряется')
add('person_trade','Торговые клиенты со связью с физлицом',t.SYNTHETIC_U.isin(l.SYNTHETIC_U).sum(),len(t),'Действующие торговые клиенты СКБ','Fid_Uid_link + Uid_data','Покрытие связями, не ролями')
add('person_records','Записи СКБ со связью с физлицом',s.SYNTHETIC_U.isin(l.SYNTHETIC_U).sum(),len(s),'Все записи СКБ','Fid_Uid_link + Uid_data','Знаменатель включает записи с неоднозначным ID')
links=l[l.SYNTHETIC_U.isin(c.SYNTHETIC_U)].drop_duplicates(['SYNTHETIC_F','SYNTHETIC_U'])
person_n=links.groupby('SYNTHETIC_F').SYNTHETIC_U.nunique()
add('multi_person_client','Люди, связанные с несколькими клиентами СКБ',person_n.ge(2).sum(),len(person_n),'Люди со связью хотя бы с одним клиентом СКБ','Fid_Uid_link','Связь с ≥ 2 различными юрлицами; не доказательство общего собственника')

# Cohorts are explicit. Company joins exclude ambiguous identifiers.
ids=set(c.SYNTHETIC_U);p['valid_endpoints']=~p.PAYER.isin(ambiguous)&~p.BENEFICIARY.isin(ambiguous)
p['same_company']=p.PAYER.eq(p.BENEFICIARY)
pp=p[p.valid_endpoints & p.PAY_AMT.gt(0) & ~p.same_company].copy()
pp['payer_group']=pp.PAYER.map(groupmap);pp['beneficiary_group']=pp.BENEFICIARY.map(groupmap)
pp['intragroup']=pp.payer_group.eq(pp.beneficiary_group)&pp.payer_group.notna()
incoming=pp[pp.BENEFICIARY.isin(ids)].groupby(['BENEFICIARY','PAYER'],as_index=False).agg(PAY_AMT=('PAY_AMT','sum'),PAY_CNT=('PAY_CNT','sum'))
total_in=incoming.groupby('BENEFICIARY').PAY_AMT.sum()
top3=incoming.sort_values('PAY_AMT',ascending=False).groupby('BENEFICIARY').head(3).groupby('BENEFICIARY').PAY_AMT.sum()
top3_share=top3/total_in
outgoing=pp[pp.PAYER.isin(ids)].copy()
total_out=outgoing.groupby('PAYER').PAY_AMT.sum()
intra_amt=outgoing.loc[outgoing.intragroup].groupby('PAYER').PAY_AMT.sum()
intra_share=intra_amt.reindex(total_out.index,fill_value=0)/total_out
external=pp[~pp.intragroup & pp.BENEFICIARY.isin(ids)].groupby(['BENEFICIARY','PAYER'],as_index=False).PAY_AMT.sum()
ext_total=external.groupby('BENEFICIARY').PAY_AMT.sum()
ext_top=external.sort_values('PAY_AMT',ascending=False).groupby('BENEFICIARY').head(3).groupby('BENEFICIARY').PAY_AMT.sum()
ext_share=ext_top/ext_total
clients=c[['SYNTHETIC_U','GROUP_ID','sector','REVENUE_COMPANY','ingroup','FTS_FLAG','FACTORING_MARK']].copy()
clients['incoming_observed']=clients.SYNTHETIC_U.map(total_in)
clients['top3_incoming_share']=clients.SYNTHETIC_U.map(top3_share)
clients['external_top3_share']=clients.SYNTHETIC_U.map(ext_share)
clients['outgoing_observed']=clients.SYNTHETIC_U.map(total_out)
clients['intragroup_outgoing_share']=clients.SYNTHETIC_U.map(intra_share)
clients['person_link']=clients.SYNTHETIC_U.isin(l.SYNTHETIC_U)
for prod in sorted(pr.PRODUCT.dropna().unique()):
    clients['product:'+prod]=clients.SYNTHETIC_U.isin(pr.loc[pr.PRODUCT.eq(prod),'SYNTHETIC_U'])
clients.to_csv(out/'client_features.csv',index=False,encoding='utf-8-sig')
wh=clients[clients.sector.eq('46')];covered=wh[wh.top3_incoming_share.notna()]
add('top3_70','Оптовые клиенты с топ-3 > 70% поступлений',covered.top3_incoming_share.gt(.7).sum(),len(covered),'Оптовые клиенты СКБ с пригодными входящими платежами','Uid_payment + Uid_data','Агрегат по плательщику; топ-3 / все наблюдаемые поступления; положительные платежи, без самого себе и неоднозначных ID')
add('top3_coverage','Покрытие оптовиков входящими платежами',len(covered),len(wh),'Все оптовые клиенты СКБ','Uid_payment + Uid_data','Отсутствие поступлений считается отсутствием данных, не нулевой концентрацией')
extwh=wh[wh.external_top3_share.notna()]
add('external_top3_70','Оптовики с внешним топ-3 > 70%',extwh.external_top3_share.gt(.7).sum(),len(extwh),'Оптовые клиенты с наблюдаемыми внешними поступлениями','Uid_payment + GROUP_ID','Из поступлений исключены известные внутригрупповые переводы; неизвестные группы не равны внешним подтверждённым связям')
gclients=clients[clients.ingroup & clients.intragroup_outgoing_share.notna()]
add('intra20','Клиенты групп с внутригрупповыми > 20%',gclients.intragroup_outgoing_share.gt(.2).sum(),len(gclients),'Клиенты СКБ в группах с пригодными исходящими','Uid_payment + GROUP_ID','Доля известных внутригрупповых исходящих среди пригодных наблюдаемых исходящих; неполнота связей может занижать долю')
ft=wh[wh.FTS_FLAG.eq(1)];ved=set(pr.loc[pr.PRODUCT.eq('ВЭД'),'SYNTHETIC_U'])
add('fts_wholesale','Оптовые клиенты с флагом ФТС',len(ft),len(wh),'Все оптовые клиенты СКБ','Uid_data: FTS_FLAG','Флаг источника, не подтверждение текущего импортного контракта')
add('fts_without_ved','Клиенты ФТС без записи ВЭД',(~ft.SYNTHETIC_U.isin(ved)).sum(),len(ft),'Оптовые клиенты СКБ с FTS_FLAG=1','Uid_product + Uid_data','Отсутствует PRODUCT=ВЭД; продукт в другом банке и потребность не определяются')
add('factoring_flag','Оптовые клиенты с флагом факторинга',wh.FACTORING_MARK.eq(1).sum(),len(wh),'Все оптовые клиенты СКБ','Uid_data: FACTORING_MARK','Флаг профиля; отдельно от продуктовой таблицы')
fact=set(pr.loc[pr.PRODUCT.eq('ФАКТОРИНГ'),'SYNTHETIC_U'])
add('factoring_product','Оптовики с продуктовой записью факторинга',wh.SYNTHETIC_U.isin(fact).sum(),len(wh),'Все оптовые клиенты СКБ','Uid_product','Иной источник и определение, чем FACTORING_MARK')
largest=outgoing.groupby(['PAYER','BENEFICIARY'],as_index=False).PAY_AMT.sum().sort_values(['PAY_AMT','BENEFICIARY'],ascending=[False,True]).groupby('PAYER').head(1).copy()
largest['payer_sector']=largest.PAYER.map(sectormap);largest['recipient_sector']=largest.BENEFICIARY.map(sectormap)
known=largest.dropna(subset=['payer_sector','recipient_sector'])
add('recipient_different','Крупнейший получатель из другого сектора',known.payer_sector.ne(known.recipient_sector).sum(),len(known),'Клиенты СКБ с сопоставимыми кодами крупнейшего получателя','Uid_payment + MAINOKVED_CODE','Отрасль по первым 2 цифрам; получатель не обязательно поставщик')

# Group composition: all available profile records of groups containing a trade client.
trade_gids=set(t.loc[t.ingroup,'GROUP_ID']);g=u[u.GROUP_ID.isin(trade_gids)].copy()
gr=g.groupby('GROUP_ID').agg(profile_records=('SYNTHETIC_U','size'),known_entities=('SYNTHETIC_U',lambda z:z[~z.isin(ambiguous)].nunique()),sectors=('sector','nunique'),full_okveds=('MAINOKVED_CODE','nunique'),revenue_rows=('REVENUE_COMPANY','count'),positive_revenue_rows=('REVENUE_COMPANY',lambda z:z.gt(0).sum()),sum_revenue=('REVENUE_COMPANY','sum'))
grp_rev=g[g.REVENUE_COMPANY.gt(0)&g.sector.notna()].groupby(['GROUP_ID','sector']).REVENUE_COMPANY.sum()
dom=(grp_rev.groupby(level=0).max()/grp_rev.groupby(level=0).sum()).rename('dominant_sector_share')
gr=gr.join(dom);gr['client_entities']=c.groupby('GROUP_ID').size().reindex(gr.index,fill_value=0);gr['trade_client_entities']=t.groupby('GROUP_ID').size().reindex(gr.index,fill_value=0)
gr['revenue_coverage']=gr.positive_revenue_rows/gr.profile_records
gr.to_csv(out/'trade_group_features.csv',encoding='utf-8-sig')
add('trade_group_mixed','Торговые группы с разными секторами',gr.sectors.gt(1).sum(),len(gr),'Группы с действующим торговым клиентом СКБ; все участники профиля','Uid_data: GROUP_ID, MAINOKVED_CODE','Разные первые 2 цифры ОКВЭД; полная база участников, а не только крупные компании')
gd=gr[gr.dominant_sector_share.notna()]
add('trade_group_dominant','Торговые группы с долей сектора ≥ 50%',gd.dominant_sector_share.ge(.5).sum(),len(gd),'Торговые группы с положительной известной выручкой и ОКВЭД','Uid_data: GROUP_ID, REVENUE_COMPANY, MAINOKVED_CODE','Максимальная сумма известной выручки сектора / сумма известной выручки; не консолидированная выручка; ≥50% допускает ничью')
complete=gr[gr.revenue_coverage.eq(1)&gr.dominant_sector_share.notna()]
add('trade_group_dominant_complete','Доминирующий сектор при полном покрытии выручкой',complete.dominant_sector_share.ge(.5).sum(),len(complete),'Торговые группы: у каждого участника известна положительная выручка','Uid_data','Отдельная проверка чувствительности к пропускам')

sectors=c.groupby('sector',dropna=False).agg(clients=('SYNTHETIC_U','size'),revenue=('REVENUE_COMPANY','sum')).reset_index().sort_values('clients',ascending=False)
sectors['client_share']=sectors.clients/len(c);sectors.to_csv(out/'sectors.csv',index=False,encoding='utf-8-sig')
products=[]
for prod in sorted(pr.PRODUCT.dropna().unique()):
    x=set(pr.loc[pr.PRODUCT.eq(prod),'SYNTHETIC_U']);products.append({'product':prod,'clients_skb':int(c.SYNTHETIC_U.isin(x).sum()),'trade_clients':int(t.SYNTHETIC_U.isin(x).sum()),'wholesale_clients':int(o.SYNTHETIC_U.isin(x).sum())})
pd.DataFrame(products).to_csv(out/'products.csv',index=False,encoding='utf-8-sig')
pd.DataFrame(metric).to_csv(out/'metrics.csv',index=False,encoding='utf-8-sig')

# Design arithmetic. No outcomes or effects are observed in these files.
N=NormalDist();za=N.inv_cdf(.975);zb=N.inv_cdf(.8)
def need(p0,p1):
    avg=(p0+p1)/2
    return math.ceil((za*math.sqrt(2*avg*(1-avg))+zb*math.sqrt(p0*(1-p0)+p1*(1-p1)))**2/(p1-p0)**2)
def mde(p0,n):
    lo=p0+1e-6;hi=min(.999,p0+.8)
    for _ in range(70):
        mid=(lo+hi)/2
        if need(p0,mid)>n:lo=mid
        else:hi=mid
    return (hi-p0)/p0
units=int((~t.ingroup).sum()+len(gr));n_t=int(units*.45);n_c=int(units*.45);n_h=units-n_t-n_c
pilot={'units':units,'solo':int((~t.ingroup).sum()),'groups':len(gr),'test':n_t,'control':n_c,'holdout':n_h,'baseline_assumption':.10,'target_assumption':.12,'alpha':.05,'power':.80,'required_per_arm':need(.10,.12),'mde_relative':mde(.10,min(n_t,n_c)),'method':'Нормальное приближение для двух независимых долей, двусторонний тест; допущение общей базовой конверсии 10%; S1/S2 имеют разные единицы, нужны отдельные базовые оценки и план объединения'}
sensitivity=[{'baseline':p0,'relative_target':.2,'target':p0*1.2,'required_per_arm':need(p0,p0*1.2),'mde_relative_available':mde(p0,min(n_t,n_c))} for p0 in [.03,.05,.10,.15,.20]]
pd.DataFrame(sensitivity).to_csv(out/'sample_size.csv',index=False,encoding='utf-8-sig')
quality={'source_manifest':manifest,'ambiguous_ids':list(ambiguous),'ambiguous_profile_rows':int(u.SYNTHETIC_U.isin(ambiguous).sum()),'ambiguous_skb_rows':int(s.SYNTHETIC_U.isin(ambiguous).sum()),'exact_duplicate_profile_rows':int(u.drop(columns=['sector','group_records']).duplicated().sum()),'ambiguous_payment_rows':int((~p.valid_endpoints).sum()),'nonpositive_payment_rows':int(p.PAY_AMT.le(0).sum()),'self_payment_rows':int(p.same_company.sum()),'usable_payment_rows':len(pp),'incoming_coverage_clients':int(clients.incoming_observed.notna().sum()),'outgoing_coverage_clients':int(clients.outgoing_observed.notna().sum()),'fields_unavailable':['Роли и права пользователей','Даты платежей','События показов и кликов','Назначение платежа','Согласия и контакты','Заявки и результаты по датам','Доход и стоимость обслуживания банка']}
base={'raw_records':len(u),'skb_records':len(s),'skb_clients':len(c),'trade_clients':len(t),'solo_trade':int((~t.ingroup).sum()),'group_trade_entities':int(t.ingroup.sum()),'trade_groups':len(gr),'wholesale_clients':len(o),'manufacturing_clients':int(c.sector.between('10','33').sum())}
result={'base':base,'metrics':metric,'pilot':pilot,'sensitivity':sensitivity,'quality':quality}
(out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=lambda x:int(x)),encoding='utf8')
print(json.dumps({'base':base,'metrics':[{k:m[k] for k in ['id','numerator','denominator','value']} for m in metric],'pilot':pilot,'quality':{k:z for k,z in quality.items() if k!='source_manifest'}},ensure_ascii=False,indent=2))
