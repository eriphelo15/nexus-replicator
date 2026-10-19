# Ineficiencias explotables en República Dominicana: inmuebles, subastas y recuperación de activos (2025-2026)

Research date: 2026-10-07. About 16 tool calls. Several primary sources (cdn.com.do, elcaribe.com.do, the Banreservas catalog PDF) returned HTTP 403, so some questions stay open (see Gaps). Exchange-rate conversions use roughly RD$60-64 per US$1. That rate is an approximation and was not checked against a source in this session.

## 1. Judicial and bank foreclosure auctions (embargo inmobiliario, Ley 189-11)

### Takeaway
The Dominican Republic has at least five separate foreclosure regimes. Ley 189-11 (2011) is the fastest. Its adjudication ruling cannot be attacked by an action for nullity or by appeal, only by cassation, and cassation does not suspend the ruling. Auction notices are spread across newspapers, court rolls and Poder Judicial bulletins, with no central search tool. Many auctions end with no bidders, and the foreclosing bank takes the property at the opening price (precio de primera puja). Those properties then come back to market as bank-owned assets (bienes adjudicados). This scattered information is a real opening for a scraper or aggregator. I found no hard figures on discounts against market value.

### Cited Findings
- Ley 189-11 (July 16, 2011), on developing the mortgage market and trusts, created a special foreclosure procedure. It is faster than the abbreviated foreclosure under Ley 6186 on agricultural development. — [vLex: El embargo inmobiliario, la Ley No. 189-11](https://do.vlex.com/vid/embargo-inmobiliario-ley-no-450231926)
- Regimes that coexist: ordinary foreclosure under the Código de Procedimiento Civil, Ley 4453 (collection of State services), the Código Tributario (tax collection), Ley 6186 (Fomento Agrícola) and Ley 189-11. — [El Caribe / search summary](https://www.elcaribe.com.do/opiniones/la-desaparicion-del-embargo-inmobiliario/) (page returned 403; content seen only in the search snippet)
- Under 189-11: partial payments by the debtor after the payment order (mandamiento de pago) do not stop the foreclosure. Incidental challenges are grouped together. The adjudication ruling "is not subject to an action for nullity or to appeal". Cassation is the only remedy and it does not suspend the ruling. Any person or company holding an express real-estate guarantee can use the procedure. — [FC Abogados](https://fc-abogados.com/ley-189-11-embargo-inmobiliario/)
- Art. 167 of Ley 189-11: the adjudication ruling can only be challenged by cassation, filed within 15 days of notification. — [vLex, Primera Sala sentencia](https://do.vlex.com/vid/sentencia-no-primera-sala-744173981)
- Real examples of opening bid prices in 189-11 auctions: RD$649,000 in one case and US$2,343,282 in another. These are set before the auction. — [vLex](https://do.vlex.com/vid/sentencia-no-primera-sala-847722261); [vLex](https://do.vlex.com/vid/sentencia-no-primera-sala-821475401)
- Court rulings record cases where the auction was declared void for lack of bidders and the foreclosing bank was declared the buyer at the opening bid price. — [Poder Judicial, Boletín Judicial](https://transparencia.poderjudicial.gob.do/documentos/pdf/BoletinJudicialIndividual/129820054.pdf); [vLex](https://do.vlex.com/vid/sentencia-no-primera-sala-812895413)
- Sale rulings are published one by one in the Poder Judicial's Boletín Judicial as PDFs. That gives a scrapeable source of auction results. — [transparencia.poderjudicial.gob.do](https://transparencia.poderjudicial.gob.do/documentos/pdf/BoletinJudicialIndividual/129820054.pdf)
- An El Caribe opinion piece titled "La desaparición del embargo inmobiliario" points to possible legal changes to the procedure. I could not read it (403). — [El Caribe](https://www.elcaribe.com.do/opiniones/la-desaparicion-del-embargo-inmobiliario/)

### Inferences
- **Why the inefficiency exists:** (a) notices appear in print or online newspapers and on separate court rolls for each district, with no national search; (b) taking possession is risky (occupants, eviction), titles can be messy (no deslinde, missing certificado de título) and liens may exist, which keeps retail buyers away; (c) the buyer usually needs cash, since bank financing for an auction purchase is not standard. The result is a thin bidder pool and frequent void auctions. Because the opening price is usually tied to the debt amount (inferred, not confirmed), properties with a low loan-to-value ratio can sell well below market.
- **Bot or data tool:** scrape the Boletín Judicial PDFs and the legal-notice sections of national newspapers (Listín Diario, Diario Libre, El Nuevo Diario, Hoy), extract the property identifiers (matrícula, parcela, DC), opening price, court and date, and cross-check against listing prices on SuperCasas/Corotos/Encuentra24 to estimate a discount. It could also run as a B2B subscription for investors and lawyers, since the ruling cannot be appealed and only cassation is possible.
- **Capital and returns:** ticket sizes run from about RD$0.6 million (US$10k) to millions of dollars. Add costs: 3% transfer tax (ITBI), legal fees and eviction. A realistic margin is unknown without a sample. Building a dataset of opening prices against comparable market prices is itself the first project worth doing.
- **Legality:** bidding at a judicial auction is legal and open. Hire a lawyer (abogado/notario) for title due diligence at the Registro de Títulos.

### Gaps
- No quantitative source on the average discount of foreclosure auctions against market value, the share of void auctions, or annual case volume.
- I could not confirm the operating rules of 189-11 from the statute text: how the opening price is set (debt amount or appraisal), deposit or guarantee required, payment deadline for the winning bidder, notice periods and whether a price reduction applies when nobody bids.
- I could not read the El Caribe article on a possible change or abolition of the embargo inmobiliario. Check whether a new Código Procesal Civil (2025-2026) changes the procedure.

## 2. Bank-owned properties (bienes adjudicados)

### Takeaway
Banreservas publishes a PDF catalog of available properties and finances up to 90% of the sale price, so a buyer needs about 10% down. The broader mortgage market is active: ExpoHogar 2025 financed more than RD$7,000 million in July. I could not confirm any Dominican bank's published discounts. The "up to 60% discount" figures that show up in searches belong to Banco Popular of Costa Rica, not Banco Popular Dominicano.

### Cited Findings
- Banreservas: bank-owned properties can be bought with financing of up to 90% of the sale price and at least 10% down. Purchase requests go in writing to ventabienesadjudicados@banreservas.com. The catalog is a PDF ("catalogo-bienes-disponibles.pdf"). — [Banreservas catálogo](https://banreservas.com/SiteAssets/Informaciones/catalogo-bienes-disponibles.pdf) (seen only via search snippet; direct download blocked)
- ExpoHogar Banreservas 2025 (July): more than RD$7,000 million financed, 1,362 properties (1,220 homes, 70 lots, 72 commercial units), rates from 7.84%. — [elDinero](https://eldinero.com.do/333133/expohogar-banreservas-2025-aprueba-financiamientos-por-mas-de-rd7000-millones/)
- More than 5,000 homes were offered at ExpoHogar Banreservas. — [El Día](https://eldia.com.do/mas-de-5000-viviendas-seran-ofertadas-en-expohogar-banreservas/)
- Warning: "discounts of up to 60%, financing up to 100%" is Banco Popular **Costa Rica** (bancopopular.fi.cr), not the Dominican bank. Do not use it for the Dominican Republic. — [Diario Extra CR](https://www.diarioextra.com/noticia/busca-propiedades-banco-popular-ofrecera-desde-1-millon/)
- INCABIDE (the state agency for seized and forfeited assets) held its first public auction on May 14, 2026: 100 of 143 lots sold (52 properties, 48 movable assets), RD$550.17 million in real estate and RD$12.665 million in movable assets (total RD$562.8 million), 345 registered participants, 4 lots void, 43 kept for later phases. The properties were in Santo Domingo (28), Santo Domingo Este (27), Santiago (8), Punta Cana and Cap Cana. — [inmobiliario.do](https://inmobiliario.do/inmuebles-subastados-por-incabide-en-primera-subasta-publica-alcanzaron-los-rd550-millones/); [Presidencia](https://presidencia.gob.do/noticias/incabide-marca-un-hito-con-exitosa-subasta-publica-y-recaudacion-superior-rd-500-millones)

### Inferences
- **Why the inefficiency exists:** each bank publishes its own catalog (often PDFs or separate microsites) in non-standard formats and without price history. Banks want to clear these non-earning assets (regulatory provisioning), which gives buyers room to negotiate. Few retail investors track them.
- **Bot or data tool:** a monitor of PDFs and microsites for Banreservas, Popular, BHD, Scotiabank, APAP, Cibao and similar lenders that normalizes price per m² and compares it with listing medians by sector. Alerts for new listings and price cuts. INCABIDE adds a new pipeline of seized assets (43 lots pending).
- **Capital:** with 90% financing from Banreservas, a RD$3 million unit needs about RD$300k down plus closing costs (3% ITBI plus about 1-2% legal and notary fees, estimated).

### Gaps
- No published discount levels for bank-owned properties at Dominican banks. Popular's and BHD's sale programs were not verified.
- INCABIDE base prices against final prices were not published in the source.

## 3. Vehicle auctions (DGA Aduanas, INCABIDE, banks, insurers)

### Takeaway
Customs (DGA) holds several public auctions a year through the agricultural commodities exchange BARD (Bolsa Agroempresarial). Lots and opening prices are published in PDFs with photos on aduanas.gob.do. Registration goes through BARD brokers (puestos de bolsa), so there is an access barrier. Opening prices for roadworthy cars look very low next to market prices: for example a 2016 Hyundai Elantra or a 2018 Kia Rio at RD$85k-176k, about US$1.4k-2.9k. Resale margins are not documented.

### Cited Findings
- Auction 02-2026 (DGA): Monday July 20, 2026, 9:00 a.m., at BARD's Salón Múltiple, C/ Euclides Morillo #51, Arroyo Hondo. Items include vehicles, motorcycles, parts, jet skis, boats, marble, fabrics and more. Viewing ran Monday to Friday at the auction warehouse on Av. Jacobo Majluta (Higüero), Haina Oriental, Caucedo and the Santo Domingo office. Bidders must register through BARD commodity brokers. Open to traders, importers, companies and the general public. — [DGA Aviso subasta 02-2026 (PDF, 77 pp.)](https://www.aduanas.gob.do/media/04ch4tz0/aviso-de-publicacion-y-fotos-subasta-02-2026.pdf)
- Opening bid prices in auction 02-2026 (from the PDF): mixed goods lots from RD$78,000 to RD$1,248,000. Lots marked "vehículo para circular" at RD$141,600, RD$85,000, RD$176,400 and RD$116,400. The PDF shows a "Hyundai Elantra 2016" next to lots 21-22 and a "Kia Rio 2018" next to lots 23-24; the layout makes the exact lot-to-price match unclear. Lots 24-26 open at about RD$4.08-4.51 million (high-end vehicles or boats, not identified). Vehicle scrap lots at RD$178,800-190,800. — [DGA PDF 02-2026](https://www.aduanas.gob.do/media/04ch4tz0/aviso-de-publicacion-y-fotos-subasta-02-2026.pdf)
- Auction 01-2025: February 19, 2025, at BARD, mixed goods and used vehicle parts. — [DGA aviso 01-2025](https://aduanas.gob.do/media/3uiapheb/aviso-de-publicacion-y-fotos-subasta-01-2025.pdf)
- The DGA also auctions "chatarras, motocicletas y vehículos en mal estado" (scrap, motorcycles and damaged vehicles) as separate auctions. — [DGA aviso chatarras](https://www.aduanas.gob.do/media/wtrdwrdw/aviso-subasta-chatarras-motocicletas-y-vehiculos-en-mal-estado-ampliacion-plazo-visita.pdf)
- Reported total: "Aduanas ha recaudado 75 millones en subastas públicas" (Customs has raised 75 million in public auctions). The article could not be read (403), so the date and details are unconfirmed. — [CDN](https://cdn.com.do/economicas/aduanas-ha-recaudado-75-millones-en-subastas-publicas/)
- INCABIDE sold 48 movable assets (vehicles among them) for RD$12.665 million in May 2026, about RD$264k per lot on average. — [inmobiliario.do](https://inmobiliario.do/inmuebles-subastados-por-incabide-en-primera-subasta-publica-alcanzaron-los-rd550-millones/)

### Inferences
- **Why the inefficiency exists:** buying requires going through a BARD broker, inspecting in person in Haina, Caucedo or Higüero during weekday hours, and reading 77-page PDFs with photos that are not searchable data. There is no prior price history and the vehicles' condition is uncertain. The opening price for a roadworthy 2016-2018 sedan (about US$1.4-2.9k) is well below typical used-car prices in the Dominican Republic. The final hammer price, any customs charges or plates (placa/marbete) still owed, and the actual condition can wipe out that gap.
- **Bot or data tool:** watch aduanas.gob.do for new notices, run OCR on the PDFs (lot, description, make, model, year, opening price), match against used-car listings on SuperCarros and Corotos for an implied discount, and alert subscribers or traders. Few people have this.
- **Capital:** RD$80k-200k per vehicle lot. Mixed goods lots of RD$0.2-1.2 million suit people who resell on Corotos or Marketplace.
- **Legality:** fully legal public auction. You need a RNC/cédula and registration with a BARD broker (broker commission not documented).

### Gaps
- Final hammer prices against opening prices, broker commission, and whether the buyer must pay ITBIS or extra customs charges on top of the winning bid.
- Bank-repossessed vehicle auctions and insurance salvage (aseguradoras) in the Dominican Republic were not researched for lack of tool calls. The Dirección General de Bienes Nacionales auction programme was not verified either.

## 4. Short-term rental (Airbnb) market

### Takeaway
Short-term rental demand is huge and growing: about 34% of the 8.86 million visitors in 2025 stayed in short-term rentals, +17.6% year on year. Supply is growing faster (+47% listings in Punta Cana-Caribers in 12 months). Median occupancy is 31-49% with an ADR of US$118-158, about US$20k a year in gross revenue against a median property price of US$220k. That is a gross yield of roughly 9% before costs, and the market is saturated. The tax regime is changing: under Decreto 30-25 (January 2025), platforms such as Airbnb must collect the 18% ITBIS, and DGII was building the collection mechanism in mid-2026.

### Cited Findings
- Punta Cana-Caribers (Airbtics, Nov 2024-Oct 2025): median occupancy 49%, ADR US$118, median annual revenue about US$20k, 4,875 active listings, +47.45% supply in 12 months, C+ investment rating. — [Airbtics](https://airbtics.com/annual-airbnb-revenue-in-punta-cana---caribers-dominican-republic-es); [Airbtics DR market review 2025](https://airbtics.com/short-term-rental-market-report-2025-the-dominican-republic)
- AirROI (Dec 2024-Nov 2025) for Punta Cana: ADR US$157.55, occupancy 30.58%, 820 listings. The two sources measure different property sets. Median price of an Airbnb-friendly property US$220,000. 5,275,474 foreign arrivals through Punta Cana airport in 2025. Hotel occupancy 84.8% in the first half of 2026. "US$20,000 is a market median, not a promise: half of all listings earned less." Not every condo allows short-term rental. — [Clic Inmobiliaria](https://clicinmobiliaria.com/en/articles/analisis-de-mercado/how-much-does-airbnb-earn-punta-cana)
- 2025: 34% of 8,860,709 visitors stayed in short-term rentals (Banco Central data). 2024: 2,564,651 non-residents. Short-term rental demand +17.6%. — [Acento](https://acento.com.do/opinion/alojamientos-de-renta-corta-superaron-a-los-hoteles-una-realidad-que-cambio-el-turismo-9683273.html)
- Decreto 30-25 (January 25, 2025): ITBIS applies to digital services from foreign providers, including digital intermediation such as Airbnb, which must register with DGII as a collection agent. In 2026 DGII was preparing the mechanism with "at least 18% ITBIS". — [Acento](https://acento.com.do/economia/dgii-prepara-cobro-de-impuestos-a-airbnb-netflix-y-plataformas-digitales-en-proximos-60-dias-9681340.html); [El Caribe](https://www.elcaribe.com.do/panorama/dinero/dgii-prepara-mecanismo-para-cobro-de-itbis-a-plataformas-digitales/); [DPL News](https://dplnews.com/republica-dominicana-advierte-sobre-posible-alza-en-factura-de-plataformas-digitales/)
- In October 2024 Airbnb declined to collect taxes in the Dominican Republic, which it does in other countries. — [Diario Libre](https://www.diariolibre.com/economia/vivienda/2024/10/31/airbnb-se-niega-a-recaudar-impuestos-en-rd-lo-hace-en-otros-paises/2898147)
- Asonahores (the hotel association) is pushing for full regulation covering licences, taxes and zoning. Regulation in La Altagracia "has not taken off". — [Acento](https://acento.com.do/turismo/asonahores-aboga-por-una-regulacion-integral-de-airbnb-que-incluya-licencias-impuestos-y-ordenamiento-territorial-9612560.html); [Acento](https://acento.com.do/turismo/crece-renta-de-airbnb-en-la-altagracia-pero-la-regulacion-del-sector-aun-no-despega-9674669.html)
- Airbnb publishes a 2025 tax guide for the Dominican Republic. — [Airbnb TaxGuide 2025 DR](https://assets.airbnb.com/help/Airbnb_TaxGuide2025_Dominican_Republic_SPANISH.pdf)

### Inferences
- **Rental arbitrage (lease long-term, sublet short-term):** with a median of US$20k gross a year (US$1,667 a month), deduct the platform fee, a coming 18% ITBIS (if passed on in full it cuts demand or margin), cleaning, utilities, management (15-25%, estimate) and furnishing. The margin over a long-term lease of US$800-1,200 a month (unsourced estimate) is thin or negative for a median listing. Arbitrage only works in the top quartile, which depends on location, design and pricing. The risk is high given +47% supply growth.
- **Barrier or opportunity:** the gap between data sources (Airbtics 49% against AirROI 31%) shows the data is poor. A local scraper that tracks Airbnb and Booking calendars by building or project, plus condo rules and Confotur status, would fill a real gap for developers and buyers. Selling data to investors in Punta Cana, Bávaro and Las Terrenas is probably more profitable than running arbitrage.
- Confotur (Ley 158-01) incentives were not researched in this session.

### Gaps
- Figures for Santo Domingo (Zona Colonial, Piantini), Las Terrenas, Cabarete or Bayahíbe.
- Exact details of Confotur (exemption from transfer tax and IPI for 15 years) and any municipal fee or tourism registration.
- Real rents for long-term leases to assess arbitrage.

## 5. Price information gap (transactions, DGII valuations)

### Takeaway
There is no public database of real transaction prices. The 3% transfer tax (ITBI) is charged on the higher of the declared price and the DGII appraisal, and DGII appraisals are usually below market. Under-declaration is a known practice, documented by the Banco Central, so even official records do not show real prices. That leaves a clear gap for valuation services (AVMs) built from listing data.

### Cited Findings
- Ley 173-07: single 3% tax on property transfers and a 2% ad valorem tax on mortgage registration. — [DGII search result / Ley 173-07](https://dgii.gov.do/legislacion/normasGenerales/Documents/NG%20sobre%20Leyes%20de%20Incentivos/norma01-09.pdf); [Century 21 Perdomo](https://c21perdomo.com/property-taxes-dominican-republic-foreign-owners/)
- ITBI is 3% of the higher of the agreed price and the DGII cadastral value. DGII appraisals are usually below market price. — [DRListings](https://www.drlistings.com/blog/dominican-republic-property-taxes/); [hacecuentas](https://hacecuentas.com/do/impuestos/comprar-vivienda)
- It is a known practice in the local market to record transactions with incomplete or incorrect data to avoid or reduce taxes (cited as documented by the Banco Central). — [CDN, "La DGII en búsqueda del peso perdido"](https://cdn.com.do/destacados/comentario-economico-la-dgii-en-busqueda-del-peso-perdido/) (seen only via search snippet)

### Inferences
- **Opportunity:** scrape and deduplicate listings (SuperCasas, Corotos, Encuentra24, Remax, Century21 and developer sites) by sector, with price per m², time on market and price cuts. Combine with auction opening prices (section 1) and bank catalogs (section 2) to flag below-market assets. Sell reports or appraisal estimates to buyers, cooperatives and fintech lenders. Capital: a laptop, servers and time. Risks: the portals' terms of use and listing quality (duplicates, stale ads).
- Tax arbitrage through under-declaration is **not** a legal opportunity and should not be recommended.

### Gaps
- Whether the Jurisdicción Inmobiliaria (ji.gob.do) gives public access to certificates or transaction prices. Not verified.
- Banco Central housing price index (if one exists) and how often it is published.

## 6. Real estate investment funds and public trusts on the BVRD

### Takeaway
Closed-end real estate funds in US dollars pay quarterly dividends of about 6% a year on their unit value, with total annualised returns around 7-9%. For example, BHD Fondos I (SIVFIC-046): unit value about US$107, dividends of US$6.1-6.6 per unit a year, vacancy around 2%, rated BBB+fa by Feller Rate. It is the passive, low-capital alternative and a benchmark the direct opportunities above must beat.

### Cited Findings
- FICI BHD Fondos I (SIVFIC-046): started November 2020. Rentals in the Dominican Republic, 6 properties, vacancy around 2%. Assets about US$29.4 million. Unit value US$104.7, US$107.5 and US$107.2 in successive periods. Dividends per unit US$6.38, US$6.56 and US$6.06. Cumulative returns of 7.3%, 9.3% and 5.5% for the periods shown. Debt at 19.0% of equity (Nov 2025), limit 50%. 230,471 units placed (23% of the programme), plus 10,529 in December 2025. A return of 8.3% annualised is cited for a multi-year period since launch. Rating BBB+fa (Feller Rate). The fund holds about 3.5% of all dollar real estate funds. — [Feller Rate / BHD Fondos, Informe semestral 2026-01 (PDF)](https://bhdfondos.com.do/wp-content/uploads/bsk-pdf-manager/2026/02/Informe-Semestral-BHD-Inmobiliario-I-2026-01.pdf); [Feller Rate ratification Jan 2025](https://bhdfondos.com.do/bf-cnt-upl/bsk-pdf-manager/2025/01/03-2025-000696-HR-Ratificacion-de-calificacion-otorgada-por-Feller-Rate-al-Fondo-de-Inversion-Cerrado-Inmobiliario-BHD-Fondos-I.pdf)
- Dividends: US$6.6 per unit in 2024 and US$6.1 in 2025, plus US$1.4 per unit approved in December 2025. — [same Feller Rate report](https://bhdfondos.com.do/wp-content/uploads/bsk-pdf-manager/2026/02/Informe-Semestral-BHD-Inmobiliario-I-2026-01.pdf)
- JMMB also manages a closed-end real estate fund (SIVFIC-012) with a 2025 annual report. Figures not extracted. — [JMMB Memoria 2025](https://do.jmmb.com/sites/default/files/JMMB%20Funds/FICI/Memoria%20Anual/Memoria%20Anual%202025%20SIVFIC-012.pdf)
- Dominican inflation (headline and core) was cited at about 4.81% and 4.75% in the same report. — [Feller Rate](https://bhdfondos.com.do/wp-content/uploads/bsk-pdf-manager/2026/02/Informe-Semestral-BHD-Inmobiliario-I-2026-01.pdf)

### Inferences
- Implied dividend yield on the unit value is about 5.7-6.1% in US$, which sets a low-effort benchmark. Possible inefficiency: units of these funds trade rarely on the secondary market at the BVRD. If a unit trades at a discount to its daily published unit value (BHD publishes "Información Diaria"), a bot could spot buy opportunities. Not verified.

### Gaps
- Secondary-market prices of the units on the BVRD against their published unit value (discounts or premiums).
- Yields of other funds (Excel, Pioneer, Popular, Reservas, Universal) and of public real estate trusts (fideicomisos de oferta pública).
