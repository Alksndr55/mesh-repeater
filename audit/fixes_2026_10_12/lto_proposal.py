"""Read-only electrical proposal; never writes CAD, model or assembly data."""
from pathlib import Path
import hashlib, json, math, xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
XML = ROOT / 'audit/independent_2026_10_12/electrical.power.xml'
MODEL = ROOT / 'design/MeshRepeater2_Power/model.json'
parts = {p['ref']: p for p in json.loads(MODEL.read_text(encoding='utf-8'))['parts']}
relevant = ['U1','U2','U8','U9','R3','R4','R47','R48','R49','R50','R51','R52','R53','R54','C58','C59','L1','C4','C12','C52','C53']
native = ET.parse(XML).getroot()
connections = {ref: {} for ref in relevant}
for net in native.findall('./nets/net'):
    for node in net.findall('node'):
        if node.get('ref') in connections:
            connections[node.get('ref')][node.get('pin')] = net.get('name')

fraction = .001 + 65 * 25e-6
def cv(rt, rb=100000):
    nominal = 2.416 * (1 + rt / rb) + 50e-9 * rt
    maximum = 2.440 * (1 + rt*(1+fraction)/(rb*(1-fraction))) + 300e-9*rt*(1+fraction)
    return {'R3_ohm':rt,'R4_ohm':rb,'CV_typ_V':nominal,'CV_static_upper_V':maximum,
            'OVP_typ_V':nominal*1.08,'OVP_static_upper_V':maximum*1.10,'static_margin_to_5_5_V':5.5-maximum*1.10}
clamp_typ = 1.24*(1+122490/100000)+.15e-6*122490
clamp_low = 1.215*(1+122490*.999/(100000*1.001))
clamp_high_estimate = 1.265*(1+122490*1.001/(100000*.999))+.9e-6*122490*1.001
thermal = []
for vcell in [2.8,2.85,3.0,3.3]:
    current = max(0,(vcell-clamp_low)/(2*.99))
    thermal.append({'cell_V':vcell,'shunt_A_estimate':current,'R2_power_W':current**2*1.98,
                    'PNP_power_W_upper_estimate':clamp_low*current,'PNP_Tj_C_estimate_Ta85_theta132':85+132*clamp_low*current})
# Conservative resistor envelope: 1% and 200 ppm/K over 65 K.
# This exceeds the actual 390-ohm Yageo specified 100 ppm/K.
rb_min = 390*(1-.01-200e-6*65)
rc_min = 47000*(1-.01-200e-6*65)
ik_bound = 5.5/rb_min + 11/rc_min
sources = [
 {'id':'lmv','url':'https://www.ti.com/lit/ds/symlink/lmv431.pdf','title':'TI LMV431 Rev G; recommended current, A-grade limits and stability'},
 {'id':'cn','url':'https://consonance-elec.com/static/upload/file/20231218/1702867485736775.pdf','title':'Consonance CN3722 Rev 1.2; FB, OVP and battery removal'},
 {'id':'tps','url':'https://www.ti.com/lit/ds/symlink/tps63802.pdf','title':'TI TPS63802 Rev D; VIN operating limit and UVLO'},
 {'id':'pnp','url':'https://assets.nexperia.com/documents/data-sheet/BCX53_SER.pdf','title':'Nexperia BCX53 Rev 11 (12 August 2026); pins, gain, thermal limits'},
 {'id':'rb','url':'https://yageogroup.com/component-documentation/download/specsheet/RC0805FR-07390RL','title':'Yageo RC0805FR-07390RL; 1%, 0.125 W, 100 ppm/K'},
 {'id':'ldo','url':'https://www.ti.com/lit/ds/symlink/tps7a26.pdf','title':'TI TPS7A26 Rev B; dropout, IQ, startup and thermal envelope'}]
added_parts = [
 {'function':'QBOOST1 / QBOOST2','quantity':2,'value':'PNP','mpn':'BCX53-16,115','package':'SOT89','pinmap':{'1':'E','2':'C','3':'B'},'purchase':'https://www.lcsc.com/product-detail/C47787.html','availability':'LCSC: part listed in stock when checked 2026-10-12; Danomsk stock unconfirmed'},
 {'function':'RB1 / RB2','quantity':2,'value':'390 ohm 1%','mpn':'RC0805FR-07390RL','package':'0805','purchase':'https://www.lcsc.com/fr/product-detail/Chip-Resistor-Surface-Mount_390R-390R-1_C114543.html','availability':'Distributor part link; stock not newly confirmed'},
 {'function':'RBE1 / RBE2','quantity':2,'value':'4.7 kohm 1%','mpn':'RC0805FR-074K7L','package':'0805','purchase':None,'availability':'Concrete manufacturer part; Danomsk exact part/stock not confirmed'},
 {'function':'RCOMP1 / RCOMP2','quantity':2,'value':'47 kohm 1%','mpn':'RC0805FR-0747KL','package':'0805','purchase':None,'availability':'Concrete manufacturer part; Danomsk exact part/stock not confirmed'},
 {'function':'CCOMP1 / CCOMP2','quantity':2,'value':'100 nF X7R','mpn':'CC0805KKX7R0BB104','package':'0805','purchase':parts['C62']['vendor_url'],'availability':'Exact Danomsk part already selected in project; stock not rechecked today'}]
proposal_channels = []
for n, hi, lo, kr, ref, u, r2, ra, rx, rl, cap in [
 (1,'BAT','LTO_MID','LTO_K1','LTO_REF1','U8','R47','R48','R49','R50','C58'),
 (2,'LTO_MID','GND','LTO_K2','LTO_REF2','U9','R51','R52','R53','R54','C59')]:
    proposal_channels.append({'channel':n,'cell_plus':hi,'cell_minus':lo,'regulated_node':kr,
      'keep':{r2:[hi,kr],ra:[kr,f'LTO_DIV{n}'],rx:[f'LTO_DIV{n}',ref],rl:[ref,lo],cap:[kr,lo]},
      'change':{f'{u}.3':f'LTO_CTRL{n}'},
      'add':{f'QBOOST{n}':{'1_E':kr,'2_C':lo,'3_B':f'LTO_BASE{n}'},
             f'RB{n}':[f'LTO_BASE{n}',f'LTO_CTRL{n}'],f'RBE{n}':[kr,f'LTO_BASE{n}'],
             f'RCOMP{n}':[f'LTO_CTRL{n}',f'LTO_COMP{n}'],f'CCOMP{n}':[f'LTO_COMP{n}',ref]},
      'unchanged_LMV_pins':{f'{u}.1':'NC',f'{u}.2':lo,f'{u}.4':ref,f'{u}.5':lo}})
data = {
 'status':'PROPOSAL ONLY — CAD, model and assembly files unchanged; not qualified for production',
 'date':'2026-10-12','scope':'Inherited E-I1 and E-I2 only; approved GPIO and 2-ohm ballast preserved',
 'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [XML,MODEL,ROOT/'design/MeshRepeater2_Power/LTO_Balancer.kicad_sch',ROOT/'design/MeshRepeater2_Power/Converter.kicad_sch']},
 'native_net_evidence':connections,
 'charger':{'formula':'VREG=VFB*(1+R3/R4)+IFB*R3; static OVP_max=1.10*VREG_max',
            'resistor_fraction':fraction,'VFB_typ_V':2.416,'VFB_max_V':2.44,'IFB_typ_A':50e-9,'IFB_max_A':300e-9,
            'approved_LTO':cv(121000),'lower_CV_comparison_NOT_a_fix':[cv(x) for x in [97600,100000,102000,103000]],
            'transient_example_NOT_a_prediction':{'formula':'sqrt(Vtrip^2 + L*Ipk^2/Ceff)','L_H':100e-6,'assumed_Ipk_A':.8,'assumed_Ceff_F':20e-6,'Vtrip_V':cv(100000)['OVP_static_upper_V'],'Vafter_V':math.sqrt(cv(100000)['OVP_static_upper_V']**2+100e-6*.8**2/20e-6)},
            'unbounded_in_source':'No maximum CN3722 OVP response delay; MLCC effective capacitance not guaranteed'},
 'booster':{'topology':'PNP emitter on node AFTER original 2 ohm; collector to cell minus; LMV cathode controls base through 390 ohm',
            'channels':proposal_channels,'added_parts':added_parts,'unchanged_divider_ohm':[120000,2490,100000],
            'threshold_typ_old_V':clamp_typ,'threshold_low_corner_V':clamp_low,'threshold_high_estimate_V':clamp_high_estimate,
            'threshold_high_limit_caveat':'0.9 uA IREF combines max at 25C and max temperature variation; not an independently tabulated guaranteed full-temperature absolute IREF.',
            'off_current_typ_estimate_per_channel_A':(2.75-1.24)/122490,
            'cathode_current_bound':{'assumed_max_cell_V':5.5,'assumed_node_voltage_range_V':[0,5.5],'capacitor_initial_range_V':[-5.5,5.5],
                  'formula':'5.5/RB_min + 11/RCOMP_min','RB_min_ohm':rb_min,'RCOMP_min_ohm':rc_min,'IK_max_A':ik_bound,
                  'qualification':'Analytical resistor bound only, including reversal of stored compensation-capacitor voltage. Does not certify stability, clamp threshold or thermal safety.'},
            'compensation_candidate':{'R_ohm':47000,'C_F':100e-9,'RC_pole_Hz':1/(2*math.pi*47000*100e-9),'qualified':False},
            'thermal':thermal,'thermal_assumption':'BCX53 thetaJA=132 K/W with >=1 cm2 collector copper; not guaranteed on actual two-layer board under lid.',
            'headroom_condition':'CTRL >= VREF and Ic/hFE + VBE/RBE <= (KREG - VBE - VREF)/RB. Gain table has no full-temperature guaranteed continuous hFE envelope.',
            'threshold_change':'Cathode operating voltage changes; LMV431 cathode-voltage coefficient changes REF by millivolts. Same resistor values are not an exact threshold equivalence.'},
 'E_I2_choices':[
   {'id':'retain','action':'Preserve approved LTO circuit','result':'E-I2 remains; solar operation with battery absent/disconnected is not qualified; no claim of 5.5 V in every situation'},
   {'id':'authorize_low_loss_OVP','action':'Authorize separate low-loss overvoltage disconnect between BAT and TPS VIN','result':'Requires new circuit decision, startup/response tolerances and energy/thermal proof; no ready implementation in this proposal'}],
 'rejected_LDO_comparison':{'mpn':'TPS7A2650DRVR','package':'WSON6 2x2 mm','pins':{'1':'OUT','2':'NC (optionally GND)','3':'PG (unused, optionally GND)','4':'EN tied IN','5':'GND','6':'IN','pad':'GND'},
      'output_V':5.0,'output_static_tolerance':.01,'output_current_max_A':.5,'IQ_no_load_typ_A':2e-6,'IQ_no_load_max_A':4.5e-6,
      'dropout_max_V_at_500mA':.590,'reason_rejected':'Conflicts with critical voltage-drop preference and limits TPS input current; output transition overshoot has no universal 5.5 V guarantee. Not recommended as ready OVP.',
      'purchase':'https://www.lcsc.com/product-detail/C2866192.html'},
 'qualification_checks':[
  'LMV cathode current and CTRL voltage at onset and 2.75/2.80/2.85 V per cell, all accepted temperatures and tolerance corners.',
  'Oscilloscope KREG, CTRL, REF and balance current; zero/high source impedance, startup, battery insertion/removal, 47 nF and compensation capacitor tolerance; no sustained oscillation.',
  'Per-channel no-balance leakage, collector copper thermal rise under cover; maintain allowed junction temperature and resistor derating.',
  'Define actual permissible individual LTO cell maximum from its datasheet; this high-impedance divider has broad corners and remains a balancer, not cell protection.',
  'For separately authorized VIN OVP: source rising/step, battery unplug at maximum charge current, light/full load, startup and converter cutoff; verify instantaneous VIN <=5.5 V over the accepted envelope.'],
 'sources':sources}
(HERE/'lto_options.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

# A deliberately simple clean connection diagram, generated from explicit net labels:
svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="1240" height="770" viewBox="0 0 1240 770">
<style>text{font-family:Arial,sans-serif;font-size:18px;fill:#203348}.s{font-size:15px}.h{font-size:25px;font-weight:bold}.w{stroke:#187044;stroke-width:3;fill:none}.p{stroke:#203348;stroke-width:2;fill:white}.j{fill:#187044}</style>
<rect width="1240" height="770" fill="white"/><text x="28" y="38" class="h">E-I1 · PNP усилитель балансира · ПРЕДЛОЖЕНИЕ</text>
<text x="28" y="68">Один канал. Силовой ток проходит через QBOOST; 2 Ω и старый делитель сохраняются.</text>
<path class="w" d="M55 135 H160 M240 135 H1100 M340 135 V235 M340 315 V370 M340 450 V600 M680 135 V210 M680 290 V360 M920 135 V260 M920 360 V600 M1100 135 V310 M1100 370 V600 M55 600 H1145 M680 360 H600 M520 360 H460 V410 M460 490 V600 M340 345 H405 V450 H420 M460 360 V310 H570 M650 310 H705 M735 310 H780 V345 H405"/>
<rect class="p" x="160" y="121" width="80" height="28"/><text x="135" y="103">R47 / R51 · 2 Ω</text><text x="55" y="170">CELL+</text><text x="995" y="115">KREG</text>
<rect class="p" x="323" y="235" width="34" height="80"/><text x="130" y="253">R48/R52 · 120k</text><text x="130" y="279">+ R49/R53 · 2.49k</text>
<rect class="p" x="323" y="370" width="34" height="80"/><text x="110" y="410">R50/R54 · 100k</text><text x="365" y="335">REF</text>
<rect class="p" x="663" y="210" width="34" height="80"/><text x="525" y="225">RBE · 4.7k</text>
<rect class="p" x="520" y="347" width="80" height="26"/><text x="590" y="396">RB · 390 Ω</text>
<rect class="p" x="420" y="410" width="110" height="80"/><text x="431" y="438">U8 / U9</text><text x="430" y="463">LMV431A</text>
<text x="462" y="405" class="s">3 K / CTRL</text><text x="398" y="465" class="s">4</text><text x="470" y="515" class="s">2/5 A</text>
<rect class="p" x="570" y="297" width="80" height="26"/><text x="520" y="278" class="s">RCOMP · 47k</text>
<path d="M705 296 V324 M735 296 V324" stroke="#203348" stroke-width="3"/><text x="705" y="250" class="s">CCOMP · 100nF</text>
<circle class="p" cx="920" cy="310" r="50"/>
<path d="M890 280 V340 M890 294 L920 270 M890 326 L920 350 M903 283 L917 286 L911 272 Z" stroke="#203348" stroke-width="2" fill="#203348"/>
<path class="w" d="M680 360 H810 V310 H890 M920 260 V270 M920 350 V360"/>
<text x="945" y="242">1 E</text><text x="830" y="294">3 B</text><text x="945" y="384">2 C</text><text x="960" y="470">BCX53-16,115</text><text x="960" y="494" class="s">SOT89 · QBOOST</text>

<path class="w" d="M1100 310 V325 M1100 355 V370"/><path d="M1084 325 H1116 M1084 355 H1116" stroke="#203348" stroke-width="3"/><text x="1130" y="340" class="s">C58/C59</text><text x="1130" y="364" class="s">47nF</text>
<path d="M670 345 H690" stroke="white" stroke-width="7" fill="none"/><path class="w" d="M680 330 V360"/><path d="M670 345 Q680 326 690 345" stroke="white" stroke-width="7" fill="none"/><path d="M670 345 Q680 326 690 345" class="w"/><circle class="j" cx="340" cy="135" r="5"/><circle class="j" cx="680" cy="135" r="5"/><circle class="j" cx="920" cy="135" r="5"/><circle class="j" cx="340" cy="345" r="5"/><circle class="j" cx="460" cy="360" r="5"/><circle class="j" cx="680" cy="360" r="5"/>
<text x="55" y="635">CELL−: верхний канал = LTO_MID; нижний = GND.</text>
<text x="28" y="679" class="s">Верхний коллектор и его медь изолированы от GND. Делитель измеряет KREG после 2 Ω, как в прежней схеме.</text>
<text x="28" y="706" class="s">Компенсация 47k + 100nF — начальная версия для квалификации. Точные сети обоих каналов: lto_options.json.</text>
<text x="28" y="733" class="s">CAD и BOM не изменены. Это не защита ячейки от перенапряжения и не испытанная схема.</text></svg>'''
(HERE/'lto_balancer_booster.svg').write_text(svg,encoding='utf-8')

rows = ''.join(f'<tr><td>{p["function"]}</td><td>{p["quantity"]}</td><td>{p["value"]}</td><td>{p["mpn"]}<br>{p["package"]}</td><td>{("<a href="+chr(34)+p["purchase"]+chr(34)+">Карточка</a><br>") if p["purchase"] else ""}{p["availability"]}</td></tr>' for p in added_parts)
tr = ''.join(f'<tr><td>{x["cell_V"]:.2f}</td><td>{x["shunt_A_estimate"]*1000:.1f}</td><td>{x["PNP_power_W_upper_estimate"]:.3f}</td><td>{x["R2_power_W"]:.3f}</td><td>{x["PNP_Tj_C_estimate_Ta85_theta132"]:.0f}</td></tr>' for x in thermal)
approved = data['charger']['approved_LTO']
lower = cv(100000)
source_links = ''.join(f'<li><a href="{s["url"]}">{s["title"]}</a></li>' for s in sources)
html = f'''<!doctype html><html lang="ru"><meta charset="utf-8"><title>LTO · решения E-I1/E-I2</title><style>
body{{font:17px/1.5 Arial,sans-serif;max-width:1150px;margin:32px auto;padding:0 20px;color:#203348;background:#f6f8fa}}
h1{{font-size:30px}}h2{{font-size:23px;margin-top:30px}}table{{width:100%;border-collapse:collapse;background:white;font-size:15px}}td,th{{border:1px solid #cbd5e1;text-align:left;padding:9px}}a{{color:#135bac}}.box{{padding:18px;border-left:5px solid #c87819;background:#fff4df}}.muted{{color:#596a7a}}img{{max-width:100%;background:white;border:1px solid #cbd5e1}}code{{background:#e8edf2;padding:2px 5px}}li{{margin:9px 0}}</style>
<h1>LTO: два унаследованных электрических риска</h1><p class="muted">12 октября 2026 · Только предложение для согласования. Схема, плата, model.json и монтажные варианты не изменялись.</p>
<div class="box"><b>E-I1 можно переработать с сохранением 2 Ω:</b> внешний PNP переносит основной ток балансировки из LMV431. Нужны проверка петли, температуры и реального порога.<br><b>E-I2 нельзя закрыть одним делителем:</b> для сохранения зарядки 5,345 В и ограничения входа TPS до 5,5 В требуется разрешить отдельный узел отсечки. До этого прежнее ограничение остаётся.</div>
<h2>E-I1: усилитель балансира</h2>
<p>Предлагается BCX53-16,115 в каждом канале: эмиттер на KREG после существующих 2 Ω, коллектор на минус своей ячейки. Новый катод CTRL управляет базой через 390 Ω; 4,7 kΩ эмиттер–база выключает транзистор и обеспечивает катодный ток при балансировке. Сохраняются 120 kΩ + 2,49 kΩ / 100 kΩ и C58/C59 = 47 nF. Верхний коллектор — LTO_MID, нижний — GND.</p>
<img src="lto_balancer_booster.svg" alt="PNP усилитель балансира"><p><a href="lto_options.json">Точные сети обоих каналов, исходные SHA256 и расчёты JSON</a> · <a href="lto_proposal.py">Воспроизводимый расчёт</a></p>
<p>Старый порог: {clamp_typ:.4f} В типично; низкий угол {clamp_low:.4f} В. При 2,80 В и 1,98 Ω расчёт требует {thermal[0]['shunt_A_estimate']*1000:.1f} мА — больше рекомендуемых 15 мА LMV431. Это демонстрирует перегрузку исходной цепи, а не предсказывает её ток вне спецификации. Добавление PNP меняет напряжение катода, поэтому прежние номиналы не гарантируют прежний порог до милливольта. Потребление отключённого делителя ориентировочно {data['booster']['off_current_typ_estimate_per_channel_A']*1e6:.2f} мкА на ячейку; утечки PNP/LMV и монтаж добавляют ток.</p>
<p>При напряжениях узлов 0…5,5 В и начальном напряжении CCOMP в пределах ±5,5 В ток катода ограничен резисторами: <code>5,5 / 381,03 + 11 / 45919 = {ik_bound*1000:.3f} мА</code>. Для резисторов консервативно суммированы 1% и 200 ppm/K × 65 K. Серийная компенсация CTRL → 47 kΩ → 100 nF → REF — начальный кандидат, RC-полюс 33,9 Гц. Этот расчёт ограничивает ток, но не доказывает устойчивость петли.</p>
<table><thead><tr><th>Новая позиция</th><th>Шт.</th><th>Номинал</th><th>MPN / корпус</th><th>Закупка / статус</th></tr></thead><tbody>{rows}</tbody></table>
<p>BCX53: выводы 1 E, 2 C, 3 B. Нельзя использовать посадку с другой распиновкой SOT89. Для тепла нужен коллекторный полигон около 1 см² на канал; у верхнего канала он электрически изолирован от общей земли. Не размещать нагревающийся транзистор вплотную к делителю REF и термистору.</p>
<table><thead><tr><th>Ячейка, В</th><th>Ток по низкому порогу, мА</th><th>PNP, Вт (верхняя оценка)</th><th>2 Ω, Вт</th><th>Tj при Ta=85 °C / θ=132 K/W</th></tr></thead><tbody>{tr}</tbody></table>
<p>θ = 132 K/W взята для медной площади 1 см² из документа Nexperia; реальная плата под крышкой может охлаждаться хуже. Режим 3,30 В перегревает и PNP, и прежний 0805 2 Ω. Переработка устраняет перенос основного тока через LMV, но не превращает балансир в защиту ячейки. Верхний расчёт порога около {clamp_high_estimate:.3f} В включает предположение IREF = 0,9 мкА; это сумма отдельных максимумов, а не отдельная гарантированная паспортная граница на всех температурах.</p>
<p>Кроме тепла, проверить запас: <code>CTRL ≥ VREF</code> и <code>Ic/hFE + VBE/RBE ≤ (KREG − VBE − VREF)/RB</code>. Таблица BCX53-16 не гарантирует единую минимальную hFE во всём диапазоне токов и температур. Поэтому режимы 2,75 / 2,80 / 2,85 В, холодный пуск, ток катода, реальные пороги и отсутствие генерации требуют образца. Минимальный ток LMV и начальная компенсация также проверяются при малом токе балансировки.</p>
<h2>E-I2: заряд LTO и предел TPS63802</h2>
<p>CN3722 имеет VFB = 2,416 В типично / 2,440 В максимум и IFB = 50 / 300 нА; OVP = 1,08 / 1,10 от заданного заряда. Существующий делитель 121 kΩ / 100 kΩ, 0,1%, ±25 ppm/K даёт:</p>
<table><tr><th>Режим</th><th>Типично</th><th>Верхняя статическая оценка, включая 65 K</th></tr><tr><td>CV с батареей</td><td>{approved['CV_typ_V']:.4f} В</td><td>{approved['CV_static_upper_V']:.4f} В</td></tr><tr><td>OVP при отсутствии батареи</td><td>{approved['OVP_typ_V']:.4f} В</td><td>{approved['OVP_static_upper_V']:.4f} В</td></tr></table>
<p>Формула CV: <code>VFB × (1 + R3/R4) + IFB × R3</code>; для температурной оценки каждого резистора суммированы 0,1% и 65 × 25 ppm/K. Рабочий максимум VIN TPS63802 — 5,5 В; абсолютный 6 В не разрешает этот обычный режим. CN3722 не задаёт максимальную задержку OVP; после прекращения управления дроссель всё ещё отдаёт энергию в конденсаторы.</p>
<p>Снижение R3 до 100 kΩ дало бы CV {lower['CV_typ_V']:.3f} В и статическую OVP {lower['OVP_static_upper_V']:.3f} В, но изменило бы утверждённую зарядку и нормальную работу балансиров. Оно не считается исправлением. Иллюстрация чувствительности: при <i>предполагаемых</i> L = 100 мкГн, пиковом токе 0,8 А и Ceff = 20 мкФ энергия даёт <code>√(5,415² + L×I²/C) = {data['charger']['transient_example_NOT_a_prediction']['Vafter_V']:.3f} В</code>. Это не модель фактического выброса, а причина не приравнивать статический делитель к ограничению любого перехода.</p>
<table><thead><tr><th>Выбор</th><th>Результат</th><th>Что требуется</th></tr></thead><tbody><tr><td>Сохранить утверждённый LTO</td><td>Заряд 5,345 В, прежний прямой BAT → VIN</td><td>E-I2 остаётся открытым; работа от солнца без батареи и её отключение под током не квалифицированы.</td></tr><tr><td>Разрешить независимую отсечку VIN</td><td>Сохранить заряд, разорвать питание TPS при повышении BAT малопотерьным ключом</td><td>Пересмотр прежнего запрета на OVP; отдельное согласование схемы, пускового состояния, допусков, скорости отсечки и остаточной энергии. Готовая квалифицированная отсечка сейчас не заявлена.</td></tr></tbody></table>
<p><b>Отклонённое сравнение:</b> TPS7A2650DRVR (фиксированные 5 В, WSON6) имеет 500 мА, IQ без нагрузки 2 мкА типично / 4,5 мкА максимум и статическую точность ±1%. Но падение достигает 590 мВ при 500 мА; он ограничивает входной ток TPS и не гарантирует любой выброс при выходе из dropout. Это расходится с требованием экономить напряжение и не рекомендуется как готовая замена OVP. Проверенный MPN доступен <a href="https://www.lcsc.com/product-detail/C2866192.html">в карточке LCSC</a>; точное наличие изменяется.</p>
<h2>Граница разрешения и проверки</h2>
<p>Общее «исправить недочёты» не отменяет прежние явные решения о 2 Ω, сохранении номиналов S4.16 и отказе от отдельной защиты. Усилитель сохраняет 2 Ω, но добавляет элементы и требует квалификации; новая отсечка меняет утверждённую цепь. Поэтому эти два пункта отделены от пяти новых исправлений V2 и вынесены на явный выбор. Оба пока не отмечены как исправленные в CAD.</p>
<p>Для усилителя обязательны осциллограммы KREG/CTRL/REF и тока, смена импеданса источника и пуск, температуры и допуски C58/C59/CCOMP, утечки и нагрев под крышкой. Для будущей отсечки: старт, скачок источника, отключение батареи при максимальном токе, режимы нагрузки и подтверждение VIN ≤5,5 В в согласованном диапазоне. Нужен паспорт фактически купленной LTO ячейки; отдельный балансир не гарантирует её предельное напряжение.</p>
<h2>Первичные источники</h2><ul>{source_links}</ul><p class="muted">Источник связности — native XML электрического аудита; JSON модели даёт MPN и закупочные ссылки. Наличие новых пассивов в ДАН не подтверждено. Этот отчёт не заменяет утверждённую схему.</p></html>'''
(HERE/'lto_options_RU.html').write_text(html,encoding='utf-8')
print(json.dumps({'written':['lto_options.json','lto_balancer_booster.svg','lto_options_RU.html'],
                  'CV_typ':approved['CV_typ_V'],'OVP_upper':approved['OVP_static_upper_V'],'IK_bound_mA':ik_bound*1000},ensure_ascii=False))
