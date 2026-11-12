# Literature search for phase 2 (2026-09-23)

Status: **draft for the user's review**. Produced by a search sub-agent (WebSearch /
WebFetch) on 2026-09-23. Items are the agent's reading of abstracts and full texts
it reports having opened; the user has not yet checked them. Nothing here reaches
the engine until the user accepts items and they are written into `intent.yaml`
as `supplied_literature`. Q = verbatim quote as reported, P = paraphrase.

Targeted at phase-1 results (run `sphingo_phase1b`): Pal→Sph pinned at its upper
bound, Pal influx required, SM→Cer consistent with zero, Cer→SM ≈ 3.8× Cer→HexCer,
sphingolipid label almost entirely from the sphinganine tracer.

## A. Tracer method and alkyne caveats

1. Thiele C, Papan C, Hoelper D, … Kuerschner L (2012). Tracing fatty acid metabolism by click chemistry. *ACS Chem Biol* 7:2004–2011. doi:10.1021/cb300414v. The method paper.
2. Thiele C, Wunderling K, Leyendecker P (2019). Multiplexed and single cell tracing of lipid metabolism. *Nat Methods* 16:1123–1130. doi:10.1038/s41592-019-0593-6. Glycerolipid-focused (hepatocytes).
3. Kuerschner L, Thiele C (2022). Tracing Lipid Metabolism by Alkyne Lipids and Mass Spectrometry: The State of the Art. *Front Mol Biosci* 9:880559. doi:10.3389/fmolb.2022.880559.
   - Q: "the diminutive alkyne group usually shows little to no impact on important metabolic properties".
   - Complete β-oxidation of an alkyne fatty acid ends in unstable propiolyl-CoA (P), so that label vanishes.
4. Alecu I, Tedeschi A, Behler N, … (2017). Localization of 1-deoxysphingolipids to mitochondria induces mitochondrial dysfunction. *J Lipid Res* 58:42–59. doi:10.1194/jlr.M068676. Alkyne sphingoid bases; alkyne-deoxy-sphinganine is not converted to canonical sphingolipids (P).
5. Gaebler A, Milan R, Straub L, … Thiele C (2013). Alkyne lipids as substrates for click chemistry-based in vitro enzymatic assays. *J Lipid Res* 54:2282–2290. doi:10.1194/jlr.D038653. Ceramide synthases accept alkyne substrates (P).
6. Gerl MJ, et al. (2016). Sphingosine-1-Phosphate Lyase Deficient Cells as a Tool to Study Protein Lipid Interactions. *PLoS One* 11:e0153009. doi:10.1371/journal.pone.0153009.
   - Q: the label is "maintained after degradation to hexadecenal and subsequent oxidation and activation to palmitoyl-CoA".
   - Q: "After 4 h of labeling about half of the pacSph was metabolized to the glycerophospholipid … PC."
   - The tracer is a clickable *sphingosine*.
7. Jamecna D, Höglinger D (2024). The use of click chemistry in sphingolipid research. *J Cell Sci* 137:jcs261388. PMID 38488070. Review.
8. **Unverified:** no published dual alkyne-sphinganine + 13C-alkyne-palmitate pulse-chase in neuroblastoma was found.

## B. Exogenous sphingoid bases

9. Smith ER, Merrill AH Jr (1995). *J Biol Chem* 270:18749–18758. doi:10.1074/jbc.270.32.18749. Exogenous sphinganine is "mostly (80-85%) acylated"; sphingosine is mainly phosphorylated and degraded (J774 cells).
10. Riboni L, Bassi R, Prinetti A, Viani P, Tettamanti G (1999). Predominance of the acylation route in the metabolic processing of exogenous sphingosine in neural and extraneural cells in culture. *Biochem J* 338:147–151. doi:10.1042/bj3380147.
    - Covers neuroblastoma lines. "N-acylation is the major metabolic fate"; S1P was under 2% of label (40 nM).
    - A related 1998 Neuro2A report (seen in search only) says acylation saturates at higher base loads and degradation rises (P).
11. The 3-ketosphinganine step is skippable, because it is rapidly reduced and does not accumulate. Textbook consensus; no primary source was opened.

## C. Desaturation, ceramide fates, turnover

12. Michel C, van Echten-Deckert G, Rother J, Sandhoff K, Wang E, Merrill AH Jr (1997). *J Biol Chem* 272:22432–22437. PMID 9312549. Desaturation happens at the dihydroceramide level; Sph→DhCer→Cer is the route to d18:1 (P).
13. Dei Cas M, et al. (2024). *J Lipid Res* 65:100517. doi:10.1016/j.jlr.2024.100517. A 3 h pulse gives mostly Cer/SM and minimal DhCer in HEK-293T, so desaturation is fast and DhCer is a small pool (P).
14. Haynes CA, Allegood JC, Wang EW, Kelly SL, Sullards MC, Merrill AH Jr (2011). Factors to consider in using [U-13C]palmitate for analysis of sphingolipid biosynthesis by tandem mass spectrometry. *J Lipid Res* 52:1583–1594. doi:10.1194/jlr.D015586. HEK293 cells, 0.1 mM label.
    - Palmitoyl-CoA was about 60% labelled by 3 h.
    - Rates of "62 ± 3, 13 ± 2, and 60 ± 11 pmol/h per mg protein" for Cer, HexCer and SM, i.e. SM:HexCer ≈ 4.6:1.
    - Palmitate does reach ceramide within hours there.
15. Hanada K, et al. (2003). Molecular machinery for non-vesicular trafficking of ceramide. *Nature* 426:803–809. doi:10.1038/nature02188. CERT transports ceramide.
16. Giussani P, et al. (2008). *BBA* 1781:40–51. doi:10.1016/j.bbalip.2007.11.002. CERT knockdown reduces Cer→SM without affecting glycosphingolipid synthesis (Q), suggesting separate channels.
17. Huitema K, van den Dikkenberg J, Brouwers JF, Holthuis JC (2004). Identification of a family of animal sphingomyelin synthases. *EMBO J* 23:33–44. doi:10.1038/sj.emboj.7600034. SMS1 is in the Golgi, SMS2 at the plasma membrane; SM synthesis also produces DAG.
18. **Unverified:** no cultured-cell SM hydrolysis rate was found.
    - Rat brain microsomal SM half-life of about 14 days (Freysz et al. 1980; search result only).
    - Kitatani K, Idkowiak-Baldys J, Hannun YA (2008), *Cell Signal* 20:1010–1018, doi:10.1016/j.cellsig.2007.12.006, is qualitative on salvage.

## D. Degradation route

19. Nakahara K, Ohkuni A, Kitamura T, Abe K, Naganuma T, Ohno Y, Zoeller RA, Kihara A (2012). The Sjögren-Larsson syndrome gene encodes a hexadecenal dehydrogenase of the sphingosine 1-phosphate degradation pathway. *Mol Cell* 46:461–471. doi:10.1016/j.molcel.2012.04.033. Q: "S1P is metabolized to glycerolipids via hexadecenal, hexadecenoic acid, hexadecenoyl-CoA, and palmitoyl-CoA."
20. Wakashima T, Abe K, Kihara A (2014). *J Biol Chem* 289:24736–24748. doi:10.1074/jbc.M114.571869. TER catalyses trans-2-hexadecenoyl-CoA → palmitoyl-CoA.
21. Stoffel W, Darr W (1974). 2-alkenal reductase. *Hoppe-Seyler's Z Physiol Chem* 355:54–60. doi:10.1515/bchm2.1974.355.1.54. Hexadecenal → hexadecanal activity. **The primary source was not opened.**
22. Sphinganine-1-P is cleaved to hexadecanal, which ALDH3A2 oxidises to palmitate. Textbook, secondary sources.

## E. Published kinetic models

23. Alvarez-Vasquez F, et al. (2005). *Nature* 433:425–430. doi:10.1038/nature03232. Yeast, BST/GMA.
24. Gupta S, Maurya MR, Merrill AH Jr, Glass CK, Subramaniam S (2011). *BMC Syst Biol* 5:26. doi:10.1186/1752-0509-5-26. C16 branch only, RAW264.7 cells.
25. Wronowska W, Charzyńska A, Nienałtowski K, Gambin A (2015). Computational modeling of sphingolipid metabolism. *BMC Syst Biol* 9:47. doi:10.1186/s12918-015-0176-9.
    - De novo synthesis enters as a ceramide inflow.
    - The lyase is an irreversible efflux.
    - Mass action for transport, Michaelis–Menten for enzymes.
26. Chiappa NF, Lal N, Botchwey EA (2025). *J Lipid Res* 66:100899. doi:10.1016/j.jlr.2025.100899. Dynamic flux estimation; model structure unverified.
27. Peripheral and unverified: a 2026 iScience multi-label paper (PMID 42006286) and arXiv 2606.13620.

## Candidate structural alternatives the search supports

1. The supplied sphinganine as a tracer pool entering at Sph, with direct N-acylation; the 3-ketosphinganine step skipped (9, 10, 12, 11, 25). Split endogenous Sph (from Pal+Ser) from the exogenous tracer.
2. Dilution of palmitoyl-CoA by unlabelled palmitate: an explicit unlabelled Pal pool, or tracer Pal only as the N-acyl donor (14).
3. Saturable ceramide synthase (Michaelis–Menten on Sph) versus mass action; at high load, flux shifts to SA1P (10).
4. DhCer→Cer irreversible and fast; expect only a lower bound on its rate (12, 13).
5. Cer→SM and Cer→HexCer as separate channels, optionally a two-pool ceramide (15, 16, 17). The fitted 3.8× is in the literature range (14).
6. Hexadecenal → Pal directly (lumped ALDH3A2 + CoA ligation + TER), keeping hexadecanal → Pal for the SA1P branch. Hexadecenal → hexadecanal drops to a low-priority option (19, 20, 21, 22). Optionally an ether-lipid escape from hexadecenal as a loss term (19).
7. The lyase route as a substantial label route into Pal/PC (6).
8. The constant Pal influx replaced by an explicit unlabelled Pal pool, making dilution observable (14).
9. Sph→SA1P mass action versus saturating acylation (9, 10).
10. Lumping Cer→S1P (ceramidase + SphK) matches published model granularity (24, 25).

## What such data cannot resolve (per the search)

- SM→Cer over 3 h: consistent with zero, but not confirmed quantitatively (18).
- Compartments: ER, Golgi and plasma-membrane pools are not observable in whole-cell extracts (15–17).
- The DhCer→Cer rate beyond a lower bound (13).
- The 3-ketosphinganine step (11).
- Label loss by β-oxidation versus other loss routes (3).
- Whether the alkyne perturbs the sphingoid-base route. No head-to-head validation of alkyne-sphinganine was found (3, 4, 7); this is a systematic uncertainty on every sphingoid-base rate.
- Absolute fluxes, which would need a cell-number or protein normalisation (14).

## Verification of the core set (2026-09-23, second sub-agent, Europe PMC records + PMC full text; quotes string-matched)

| item | status | correction to the claim above |
|---|---|---|
| 9 Smith & Merrill 1995 | VERIFIED (abstract) | the sphinganine is cell-made (de novo burst after a medium change), **not exogenous** |
| 10 Riboni et al. 1999 | VERIFIED (abstract) | exogenous **sphingosine**, not sphinganine; "in all cell types" incl. fibroblasts |
| 12 Michel et al. 1997 | PARTIAL | DOI is 10.1074/jbc.272.36.22432; "desaturation at the dihydroceramide level" verified; "free sphinganine is not desaturated" UNVERIFIED (full text behind a bot wall) |
| 14 Haynes et al. 2011 | VERIFIED (abstract) | none |
| 6 Gerl et al. 2016 | VERIFIED (full text) | clickable *sphingosine* (pacSph), wild-type HeLa |
| 25 Wronowska et al. 2015 | VERIFIED (full text) | "not via 3-ketosphinganine" is implied (de novo modelled as a ceramide inflow), not stated; S1P step is "irreversible S1P degradation" |

Verbatim quotes kept for `supplied_literature`:
- 9: "sphinganine was mostly (80-85%) acylated and incorporated into dihydroceramide and complex sphingolipids, whereas most of the sphingosine (70%) was phosphorylated and degraded, with incorporation of the resulting ethanolamine phosphate into phosphatidylethanolamine."
- 10: "[3H]Sphingosine 1-phosphate accounted for less than 2% of the total radioactivity incorporated in all cases. Throughout the pulse period and in all cell types, 3H-labelled organic metabolites largely prevailed over 3H2O, indicating that N-acylation is the major metabolic fate of sphingosine in these cells under apparently physiological conditions."
- 12: "These studies have conclusively established the pathway of ceramide synthesis via desaturation of dihydroceramide and have uncovered several properties of this reaction that warrant further consideration for their relevance to both sphingolipid metabolism and signaling."
- 14: "For HEK293 cells incubated with 0.1 mM [U-¹³C]palmitic acid, ∼60% of the total palmitoyl-CoA was ¹³C-labeled by 3 h (which was near isotopic equilibrium); with this correction, the rates of de novo biosynthesis of C16:0-ceramide, C16:0-monohexosylceramide, and C16:0-sphingomyelins were 62 ± 3, 13 ± 2, and 60 ± 11 pmol/h per mg protein, respectively"
- 6: "pacSph’s photoactivatable and clickable group contained in the sphingoid base hydrocarbon chain are maintained after degradation to hexadecenal and subsequent oxidation and activation to palmitoyl-CoA" / "After 4 h of labeling about half of the pacSph was metabolized to the glycerophospholipid (GP) phosphatidylcholine (PC) in Sgpl1 +/+ cells ( Fig 1A and 1B )."
- 25: "CER synthesis via de novo pathway is described as the inflow of these molecules into the endoplasmic reticulum." / "Finally, our model includes the reaction of irreversible S1P degradation." / "The kinetics of our model is based on Mass Action Law (MAL) for molecular transport reactions and the Michaelis Menten (MM) approach for enzymatically catalyzed reactions."
