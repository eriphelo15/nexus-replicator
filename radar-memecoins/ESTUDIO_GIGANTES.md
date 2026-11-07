# Estudio de gigantes: qué tenían en común las memecoins de Solana que subieron miles de %

Fecha: 2026-09-28. Datos gratuitos de CoinGecko (listado y velas diarias de 1 año) y de
GeckoTerminal (velas de 5 min y de 1 h desde el nacimiento, solo para tokens nacidos desde
abril de 2026, porque su historia gratuita no llega más atrás).

## 1. Casi todas acaban en cero

Listado de 2,220 memecoins de Solana de CoinGecko (desde 2021):

| Máximo histórico de capitalización | Tokens | Caída mediana desde su máximo | Hoy > 50% del máximo | Hoy > 10% del máximo |
|---|---|---|---|---|
| $1M o más | 1,347 | -99.5% | 19 | 112 |
| $10M o más | 554 | -99.6% | 5 | 42 |
| $100M o más | 120 | -99.5% | 2 | 9 |
| $1,000M o más | 18 | -97.3% | 0 | 1 |

**Ningún gigante se mantiene: la salida importa tanto como la entrada.** (Sesgo: CoinGecko ya
ha quitado del listado muchos tokens muertos, así que la realidad es aún peor.)

## 2. Qué pasa después del máximo (velas diarias, 116 gigantes de los últimos 12 meses)

Memecoins que pasaron de $5M con su máximo en los últimos 12 meses (velas diarias de CoinGecko):

- Del listado en CoinGecko al máximo: mediana de 18 días y x3.9.
- **Hoy valen una mediana del 3% de su máximo.**
- Del techo a -50%: mediana de **6 días**; a -80%: 18 días; a -90%: 26 días.
- **Ninguno de los 111 que cayeron un 50% desde su máximo volvió a superarlo.** El mejor
  rebote mediano después de esa caída no pasa del 50% del máximo.
- Día de más volumen frente al día del techo: el mismo día en 30 de 116; de 1 a 3 días antes en
  21; después en 22; y en 42 fue mucho antes (normalmente el día del lanzamiento). El volumen
  récord avisa del techo en menos de la mitad de los casos: sirve como aviso, no como regla.
- Stop móvil diario (activado al llegar a 3x sobre el precio de listado; 74 tokens): cuánto se
  captura del precio máximo:

| Stop desde el máximo | Captura mediana del máximo |
|---|---|
| 30% | 54% |
| 40% | 42% |
| 50% | 39% |
| 60% | 33% |
| Aguantar hasta hoy | 3% |

Con velas diarias; con velas de 1 h o 5 min el stop se ejecutaría antes y algo mejor, salvo en
desplomes de una sola vela.

## 3. Tres tipos de "gigante" (48 nacidos desde abril, analizados desde su nacimiento)

| Tipo | Ejemplos | Qué pasa |
|---|---|---|
| **Capitalización ficticia** (10 de 40 nuevos) | KNOTS, KEDAENGE, CHARACCON, USWR, NTFS | Nacen valiendo millones con casi nada de volumen: pool montado a mano. Descartar siempre (volumen de 24 h < 10% de la capitalización). |
| **Rápidos** ($1M en horas) | SCAM, ASTEROID, PISTACIO, STONKLESS, CHIMERICA, SPCTROLL | 7 de 13 marcaron su máximo el primer día y 12 de 13 están hoy por debajo del 10% de su máximo, aunque algunos movieron $5-13M en su primera hora. |
| **Rápidos que siguieron subiendo** | PAID, fone, ALLINU, EMBER, SI, OTC | Máximo de 1.5 a 10 días después del lanzamiento, volumen de la primera hora de $3-9M con precio en zigzag (54% de velas al alza, no escalera). |
| **Lentos / resucitados** ($1M tras semanas) | **ANSEM** ($392M), GOLD, MANIFEST, KET, OGDOGE, RAYCAT, TBB | Estuvieron "muertos" (caídas del 60-96%) y resucitaron una o varias veces. ANSEM tardó 62 días en llegar a $1M. Son los que más conservan: ANSEM 42% de su máximo, GOLD 96%, MANIFEST 59%. |

Frente a 21 parecidos que murieron (mismas fechas y tamaño inicial): volumen de la primera hora
$3.0M frente a $216K; velas al alza en las 3 primeras horas 54% frente a 89% (escalera de
microcompras); capitalización a las 6 h $1.6M frente a $2K; nombres de famosos y noticias entre
los muertos.

## 4. Momento del mercado

Máximos de memecoins (≥$10M) por mes: 115 en noviembre de 2024 (SOL de $168 a $238), luego se
enfrían con SOL. En 2026, con SOL de $72 (julio) a ~$122 (septiembre), vuelven a subir: 6, 9,
12 y 14 al mes de junio a septiembre. El mercado se está calentando.

## 5. Qué cambia en el radar

1. **Escáner de supervivientes** (`radar_memes/supervivientes.py`): tokens de 3 a 120 días con
   volumen real que despiertan, sin ser gigantes caídos.
2. **Motor de salida** (`radar_memes/salidas.py`): stop móvil del 30% desde el máximo como regla
   principal, aviso cuando el volumen marca récord, y fuera sin excepción si cae un 50% desde el
   techo o si retiran liquidez.

## Limitaciones

- Selección por resultado: se estudian los que llegaron lejos; no se sabe cuántos parecidos
  murieron sin llegar. Esa tasa base la medirá el propio radar.
- Detalle minuto a minuto solo desde abril de 2026; antes, solo velas diarias o el listado.
- Muestras pequeñas (decenas de tokens): patrones, no leyes.

Scripts y datos del estudio: `estudios/gigantes/` (`historia.py` reconstruye cada token desde
su nacimiento con GeckoTerminal; `diario.py` analiza las velas diarias de CoinGecko).
