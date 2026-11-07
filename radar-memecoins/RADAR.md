# Radar de memecoins (Solana)

Registra los tokens nuevos de Solana y vuelve a mirarlos a los **30 min, 1 h, 6 h y 24 h**
para medir con datos reales qué señales separan a los que se duplican de los que mueren.
**No compra ni vende nada.**

## Cómo funciona

1. **Escaneo:** lee los pools nuevos y en tendencia de GeckoTerminal. Registra cada token con
   una actividad mínima (capitalización de $10K a $5M, liquidez de al menos $5K, menos de
   24 h de vida y al menos 25 compradores en la última hora). A cada uno le pasa RugCheck y
   consulta en GeckoTerminal sus holders: cuántos hay, qué % tienen los 10 mayores y si las
   autoridades de mint y freeze están revocadas.
   - **Narrativa:** clasifica cada token por su nombre (videojuegos, IA, política, Elon,
     celebridades, animales, cripto) en `radar_memes/narrativas.py`. Mide el **calor** (cuántos
     tokens del mismo tema hay en el escaneo) y si el token es el **líder** de su narrativa
     (el de más liquidez) o un seguidor/clon.
   - **Catalizadores:** fechas de eventos por narrativa en `radar_memes/catalizadores.json`
     (lanzamiento de GTA 6, elecciones de EE. UU., festividades). Se pueden añadir más editando
     ese archivo.
   - **Palabras calientes:** cuántos tokens del escaneo comparten palabra con el token. Así se
     detectan temas nuevos que no están en la lista (p. ej. "Newscum" apareció en 17 tokens a la
     vez antes de añadirlo a política).
   - **Carteras compradoras:** guarda las carteras que compraron cada token (compras de $100 o
     más) en `carteras.csv`, para encontrar las que entran temprano una y otra vez en los que
     luego suben.
2. **Filtro v1:** marca qué tokens habría elegido el filtro. **Es una hipótesis, no una
   recomendación**; se registran también los descartados para poder compararlos.
   Criterios (en `radar_memes/escaner.py`, `FILTRO`):
   - Sin peligros en RugCheck y sin otro token con el mismo símbolo (clones). Si RugCheck no
     responde (pasa a menudo), el token no se descarta: queda como "sin datos" en el informe.
   - Capitalización de $50K a $1.5M.
   - Liquidez entre el 8% y el 60% de la capitalización.
   - Volumen de 1 h de como mucho 3 veces la capitalización (más que eso suele ser volumen falso).
   - Al menos 100 compradores en 1 h, y entre 1.2 y 8 compradores por cada vendedor.
   - Los 10 mayores holders con un 35% del suministro como mucho, y autoridades de mint y
     freeze revocadas. Sin datos de holders, no se descarta.
3. **Seguimiento:** precio, liquidez y si el token sigue vivo a los 30 min, 1 h, 6 h, 24 h,
   3 días y 7 días (muerto = precio al 10% o menos del de detección). A las 24 h descarga las
   velas de 5 min y calcula el máximo alcanzado y el resultado de la regla de salida:
   - Vender 50% a 2x, 20% a 5x y 20% a 10x, y dejar el 10% restante.
   - Salir de todo si cae a −50%. Se ejecuta al peor precio entre el stop y el cierre de la
     vela: en un rug pull nadie vende a −50%.

   A los 7 días descarga velas de 1 h y mide el máximo alcanzado (¿llegó a 10x, 50x, 100x?) y
   la **regla de tendencia**, pensada para no cortar las subidas grandes:
   - Vender 1/3 a 3x (recuperas lo invertido).
   - El resto, con stop móvil: salir si cae un 50% desde el máximo alcanzado.
4. **Informe:** `INFORME.md` compara resultados por filtro, narrativa (líder frente a
   clones, calor, catalizador), carteras inteligentes, concentración de holders, edad,
   capitalización, compradores/vendedores, volumen, RugCheck y DEX, con un 3% de costes por
   operación. También incluye:
   - **Carteras inteligentes:** las que tienen 3+ tokens con resultado y al menos la mitad
     llegó a 2x. Para cada token cuenta solo el historial conocido en el momento de detectarlo,
     sin mirar al futuro.
   - **Palabras calientes** de las últimas 3 h frente a las 24 h anteriores.
   - **Narrativas activas** de las últimas 2 h y su token líder.
   - **Señales de desplome (cuándo salir):** cada ciclo guarda una foto de 5 min de cada token
     vivo detectado en las últimas 12 h (`serie.csv`: precio, liquidez, compras/ventas). El
     informe mide, en tokens que ya subieron un 50% o más, con qué frecuencia llega un desplome
     (caída a un 40% o menos en 30 min) cuando está activa cada señal: liquidez menor al 3% de
     la capitalización, volumen de microcompras, compras muy desbalanceadas, subida de más del
     100% en 1 h, "escalera" sin retrocesos, aceleración final o más vendedores que
     compradores. Son las señales que se vieron antes de los desplomes de GTA 6 Coin y
     MetaMuse; el informe dirá si se repiten.

## Vigía: alertas en los primeros minutos

`radar_memes/vigia.py` corre en paralelo al ciclo principal. Cada minuto lee los pools recién
creados (GeckoTerminal los muestra a los pocos segundos) y vuelve a mirar, hasta sus 15 min
de vida, los que ya tienen actividad. Alerta cuando un token cumple los **criterios tempranos
v1** (hipótesis, en `TEMPRANO`):

- De 2 a 15 min de vida, capitalización de $8K a $400K y liquidez de al menos $5K.
- En los últimos 5 min: 40+ compradores, entre 1.3 y 8 compradores por vendedor, 4,000$+ de
  volumen y un ticket medio de 25$ o más (por debajo suelen ser bots de microcompras).
- No es un clon de un símbolo ya visto en las últimas 24 h.
- Vetos: cualquier riesgo que RugCheck califique de peligro (holder dominante, top 10
  concentrado, liquidez sin bloquear, historial de rug pulls del creador…), autoridades
  activas, top 10 de holders por encima del 40%, **más liquidez que capitalización** (pool
  montado a mano) y, fuera de la curva de pump.fun, **menos del 50% de la liquidez bloqueada**.
  Los tres últimos se añadieron tras Neartkt: se lanzó directamente en PumpSwap con liquidez
  sin bloquear y su creador la retiró.

**Avisos al móvil de lanzamientos: desactivados** desde el 29-09-2026 (`AVISAR_LANZAMIENTOS`). De
las 22 primeras alertas con tema y sin vetos, la mediana iba -65% a la hora y ninguna llegó a 2x
en 6 h. El vigía sigue registrándolas para medir, y los avisos al móvil quedan para los
supervivientes y el motor de salida.

**Tema del token:** se clasifica por el símbolo y, si no basta, por el nombre y la descripción
del token (p. ej. Neartkt hablaba del ETF de NEAR). **Solo se avisa al móvil si el tema es
relevante**: videojuegos, IA, política, Elon, celebridades, festividades o noticias cripto
(ETFs, reguladores, listados), o una palabra que ya aparece en 3+ tokens de las últimas 3 h.
Las alertas sin tema se registran en silencio (`prioridad` = baja, `avisado` = 0) para poder
comparar. Ojo: tener tema no es garantía; los estafadores se cuelgan de las noticias más
calientes, y una cuenta de X en la ficha puede ser una suplantación.

Cada alerta se guarda en `alertas.csv` y se sigue como cualquier detección, así que el informe
compara las alertas con el escaneo normal, las de tema relevante con las silenciosas, y
muestra las últimas 6 h.

## Supervivientes: tokens de días o semanas que despiertan

`radar_memes/supervivientes.py` sale del estudio de gigantes (`ESTUDIO_GIGANTES.md`): los que
suben en sus primeras horas casi siempre marcan su máximo el primer día y acaban en cero,
mientras que los gigantes que conservan valor (ANSEM, GOLD, MANIFEST…) tardaron semanas en
despegar, a menudo después de "morir" y resucitar. Una vez por hora el ciclo revisa los pools
con más volumen de 24 h y en tendencia de 6 h/24 h, y registra los que cumplen los **criterios
v1** (hipótesis, en `CRITERIOS`):

- De 3 a 120 días de vida, capitalización de $300K a $30M, liquidez de $30K o más.
- **Volumen real:** volumen de 24 h de 0.3 a 10 veces la capitalización (por debajo de 0.1 es
  una capitalización ficticia de un pool montado a mano).
- **Despierta:** sube un 30% o más en 24 h y el 40%+ del volumen del día es de las últimas 6 h;
  300+ compradores en 24 h y al menos tantos compradores como vendedores.
- **No es un gigante caído que rebota:** el precio está al menos al 50% de su máximo previo
  (ninguno de los 111 gigantes que cayeron un 50% desde su techo lo recuperó).
- Los mismos vetos del vigía (RugCheck, holders concentrados, autoridades, liquidez sin
  bloquear), salvo el de liquidez/capitalización < 0.7, que solo vale para lanzamientos.

Los que pasan se avisan al móvil ("Superviviente: …", como mucho 3 por hora) y se guardan en
`supervivientes.csv`; los vetados también se guardan, sin avisar. Se siguen como cualquier
detección y el informe tiene su propia sección.

## Motor de salida: avisos para vender lo que tienes

`radar_memes/salidas.py` corre dentro del vigía y revisa cada 2 minutos los tokens en los que
estás posicionado. Se maneja desde la app de ntfy: suscríbete al tema **`<tu tema>-cartera`**
(el mismo tema de las alertas con `-cartera` al final) y publica en él:

- El **contrato** del token (o `+contrato`): empieza a vigilarlo; la entrada es el precio de ese
  momento. Te confirma con "Vigilando …".
- `-contrato` o `vendí contrato`: deja de vigilarlo.
- `lista`: te responde con cada posición, su múltiplo desde la entrada y su distancia al máximo.

Avisos (en el tema de siempre), con las reglas del estudio de gigantes:

- **SAL YA** si cae un **30% desde el máximo** alcanzado desde tu entrada (stop móvil: con
  velas diarias capturaba un 54% del máximo frente a un 3% de aguantar), si cae un **50%**
  (ninguno de los 111 gigantes que cayó así volvió a su máximo) o si **retiran liquidez** (cae a
  la mitad o por debajo de $1,000).
- **Atención** (no es orden de venta):
  - **Escalera:** 30 min subiendo sin un solo retroceso de 5 min. En la serie del radar precedió
    un desplome (caída al 40% o menos en 30 min) el 46% de las veces, frente al 2% sin ella.
  - **Subida de +100% en 1 h** (desplome el 13% de las veces frente al 1%).
  - Volumen de 24 h en récord con el precio ya x2 o más (el techo suele llegar ese día o poco
    antes).
  - Presión de venta fuerte: más del doble de vendedores que compradores en 5 min y -20% en 1 h.

Las posiciones se guardan en `posiciones.json` y cada aviso en `salidas.csv` (precio, entrada y
máximo), para medir si salir fue acertado. El radar revisa cada 2 minutos: en un rug pull de un
solo bloque ningún aviso llega a tiempo.

**Avisos al móvil:** con la app gratuita [ntfy](https://ntfy.sh) suscrita a un tema, y ese
mismo tema guardado en el secreto `NTFY_TOPIC` del repositorio (*Settings* → *Secrets and
variables* → *Actions*). Sin el secreto, el vigía registra las alertas pero no avisa. El tema
debe ser secreto: quien lo conozca podría leer las alertas o publicar alertas falsas.

## Dónde verlo

GitHub Actions lo ejecuta cada 5 minutos (`.github/workflows/radar.yml`) y guarda los datos
en la rama **`radar-datos`**. Cada ejecución dura unas 5 h 40 min, con un ciclo cada 5 minutos,
y al terminar se relanza sola; la programación de GitHub (cada 30 min) queda de respaldo por si
la cadena se corta. Para pararlo: *Actions* → *Radar memecoins* → *…* → *Disable workflow*.

- `INFORME.md`: el informe, legible desde el móvil en GitHub.
- `detecciones.csv` y `seguimiento.csv`: los datos en bruto.

Para arrancarlo (o reanudarlo si se cortó): *Actions* → *Radar memecoins* → *Run workflow*.

## En tu ordenador

```bash
pip install pandas tabulate
python radar.py ciclo --cada 300     # cada 5 minutos, datos en datos_radar/
python radar.py informe              # regenerar solo el informe
```

## Cómo leer los resultados

- **No saques conclusiones de grupos con menos de 30 tokens** (el informe los marca).
- Lo que importa es `regla_$_por_50`: la ganancia o pérdida media por apuesta de $50 ya
  descontados los costes. Si el grupo *pasa* del filtro no es claramente positivo tras
  cientos de tokens, el filtro no tiene ventaja.
- Limitaciones:
  - Solo ve lo que listan las APIs públicas, y con minutos de retraso respecto a los bots.
  - RugCheck y la ficha de holders se consultan como mucho para 30 tokens nuevos por escaneo, y
    las carteras para 15,
    por los límites de las APIs. El dato de holders de GeckoTerminal puede tener minutos u
    horas de antigüedad (columna `holders_antig_min`).
  - Las narrativas se deducen solo del nombre: no hay acceso a X/Twitter ni a Telegram.
  - Si un token cambia de pool (por ejemplo, de pump.fun a PumpSwap), el radar junta las
    velas de los dos pools.
