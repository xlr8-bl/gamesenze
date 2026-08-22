/**
 * Visual identity for competitions and clubs.
 *
 * A football product that renders every fixture in the same grey is a product
 * that looks like a spreadsheet. The calendar has character: a Champions
 * League midweek does not look like a Championship Tuesday, and the site
 * should not pretend otherwise.
 *
 * What is here is colour, not iconography. Club crests and competition marks
 * are trademarks we do not have a licence to redistribute, so nothing here
 * ships one. Each club gets a monogram in its own colours, which is legally
 * clean, renders instantly at any size, and never 404s. `art` is the slot a
 * licensed image drops into later without touching a component.
 */

export type CompetitionIdentity = {
  key: string;
  name: string;
  short: string;
  /** Primary colour, used for rules, monograms and banner light. */
  accent: string;
  /** Second stop of the banner gradient. */
  accent2: string;
  country: string;
  /** Ranks the competition rail and picks the hero fixture. */
  weight: number;
  /** Optional licensed banner art, once there is any. */
  art?: string;
};

const C = (
  key: string, name: string, short: string,
  accent: string, accent2: string, country: string, weight: number,
): CompetitionIdentity => ({ key, name, short, accent, accent2, country, weight });

/**
 * Colours are drawn from each competition's own broadcast palette. They stand
 * in for the mark rather than reproducing it.
 */
export const COMPETITIONS: CompetitionIdentity[] = [
  C("ucl", "UEFA Champions League", "UCL", "#1B70E0", "#0B1F52", "Europe", 100),
  C("uel", "UEFA Europa League", "UEL", "#FF7A18", "#4A1E05", "Europe", 90),
  C("uecl", "UEFA Europa Conference League", "UECL", "#00C67A", "#053521", "Europe", 80),
  C("premier_league", "Premier League", "EPL", "#C9268F", "#2B0A38", "England", 75),
  C("la_liga", "La Liga", "LAL", "#FF5A36", "#3D1109", "Spain", 70),
  C("serie_a", "Serie A", "SEA", "#1E9BF0", "#04213D", "Italy", 68),
  C("bundesliga", "Bundesliga", "BUN", "#E8202A", "#3A0509", "Germany", 66),
  C("ligue_1", "Ligue 1", "LI1", "#C9F73D", "#232B06", "France", 62),
  C("eredivisie", "Eredivisie", "ERE", "#FF8A1E", "#3A1D03", "Netherlands", 50),
  C("primeira_liga", "Primeira Liga", "PRI", "#00A85A", "#032918", "Portugal", 48),
  C("championship", "Championship", "CHA", "#7B5BE0", "#1B1040", "England", 44),
  C("fa_cup", "FA Cup", "FAC", "#E0243C", "#33060D", "England", 40),
  C("efl_cup", "League Cup", "EFL", "#3D8BFF", "#0A1B3D", "England", 36),
  C("copa_del_rey", "Copa del Rey", "CDR", "#F2B705", "#332600", "Spain", 34),
  C("coppa_italia", "Coppa Italia", "COP", "#2ECC9E", "#052B22", "Italy", 32),
  C("dfb_pokal", "DFB Pokal", "DFB", "#F25C05", "#331302", "Germany", 30),
  C("coupe_de_france", "Coupe de France", "CDF", "#2B6EE8", "#07173A", "France", 28),
];

const BY_NAME = new Map(COMPETITIONS.map((c) => [c.name.toLowerCase(), c]));

/** Anything we do not recognise still gets a usable identity, never a crash. */
export const FALLBACK_COMPETITION: CompetitionIdentity = {
  key: "other", name: "Football", short: "FTB",
  accent: "#7C8CA6", accent2: "#151C27", country: "", weight: 0,
};

export function competitionIdentity(name: string | null | undefined): CompetitionIdentity {
  if (!name) return FALLBACK_COMPETITION;
  return BY_NAME.get(name.toLowerCase()) ?? FALLBACK_COMPETITION;
}

/* ---------------------------------------------------------------------------
   Clubs
--------------------------------------------------------------------------- */

export type ClubIdentity = { abbr: string; primary: string; secondary: string };

/**
 * `[abbreviation, primary, secondary]` per club. The abbreviation is the one a
 * supporter would actually use, not the first three letters: LIV, not LIV for
 * Livingston and Liverpool both.
 */
const CLUBS: Record<string, [string, string, string]> = {
  // England
  "Arsenal": ["ARS", "#EF0107", "#FFFFFF"],
  "Aston Villa": ["AVL", "#95BFE5", "#670E36"],
  "Bournemouth": ["BOU", "#DA291C", "#000000"],
  "Brentford": ["BRE", "#E30613", "#FBB800"],
  "Brighton & Hove Albion": ["BHA", "#0057B8", "#FFCD00"],
  "Burnley": ["BUR", "#6C1D45", "#99D6EA"],
  "Chelsea": ["CHE", "#034694", "#FFFFFF"],
  "Crystal Palace": ["CRY", "#1B458F", "#C4122E"],
  "Everton": ["EVE", "#003399", "#FFFFFF"],
  "Fulham": ["FUL", "#FFFFFF", "#000000"],
  "Ipswich Town": ["IPS", "#3A64A3", "#DE2C37"],
  "Leeds United": ["LEE", "#FFCD00", "#1D428A"],
  "Leicester City": ["LEI", "#003090", "#FDBE11"],
  "Liverpool": ["LIV", "#C8102E", "#00B2A9"],
  "Manchester City": ["MCI", "#6CABDD", "#1C2C5B"],
  "Manchester United": ["MUN", "#DA291C", "#FBE122"],
  "Newcastle United": ["NEW", "#241F20", "#FFFFFF"],
  "Nottingham Forest": ["NFO", "#DD0000", "#FFFFFF"],
  "Southampton": ["SOU", "#D71920", "#FFFFFF"],
  "Sunderland": ["SUN", "#EB172B", "#FFFFFF"],
  "Tottenham Hotspur": ["TOT", "#132257", "#FFFFFF"],
  "West Ham United": ["WHU", "#7A263A", "#1BB1E7"],
  "Wolverhampton Wanderers": ["WOL", "#FDB913", "#231F20"],
  "Birmingham City": ["BIR", "#0000FF", "#FFFFFF"],
  "Blackburn Rovers": ["BLB", "#009EE0", "#FFFFFF"],
  "Bolton Wanderers": ["BOL", "#263C7E", "#FFFFFF"],
  "Bristol City": ["BRC", "#E21C38", "#FFFFFF"],
  "Cardiff City": ["CAR", "#0070B5", "#FFFFFF"],
  "Charlton Athletic": ["CHA", "#D4021D", "#FFFFFF"],
  "Coventry City": ["COV", "#78D0F3", "#FFFFFF"],
  "Derby County": ["DER", "#FFFFFF", "#000000"],
  "Hull City": ["HUL", "#F5A12D", "#000000"],
  "Lincoln City": ["LIN", "#D3122A", "#FFFFFF"],
  "Middlesbrough": ["MID", "#E21A23", "#FFFFFF"],
  "Millwall": ["MIL", "#001D5E", "#FFFFFF"],
  "Norwich City": ["NOR", "#FFF200", "#00A650"],
  "Portsmouth": ["POR", "#001489", "#FFFFFF"],
  "Preston North End": ["PNE", "#B2B2B2", "#003399"],
  "Queens Park Rangers": ["QPR", "#1D5BA4", "#FFFFFF"],
  "Sheffield United": ["SHU", "#EE2737", "#000000"],
  "Stoke City": ["STK", "#E03A3E", "#FFFFFF"],
  "Swansea City": ["SWA", "#FFFFFF", "#000000"],
  "Watford": ["WAT", "#FBEE23", "#ED2127"],
  "West Bromwich Albion": ["WBA", "#122F67", "#FFFFFF"],
  "Wrexham": ["WRE", "#E4002B", "#FFFFFF"],

  // Spain
  "Athletic Club": ["ATH", "#EE2523", "#FFFFFF"],
  "Atlético Madrid": ["ATM", "#CB3524", "#262E62"],
  "Barcelona": ["BAR", "#A50044", "#004D98"],
  "Celta Vigo": ["CEL", "#8AC3EE", "#FFFFFF"],
  "Deportivo Alavés": ["ALA", "#0761AF", "#FFFFFF"],
  "Deportivo La Coruña": ["DEP", "#0072C6", "#FFFFFF"],
  "Elche": ["ELC", "#00854A", "#FFFFFF"],
  "Espanyol": ["ESP", "#0072CE", "#FFFFFF"],
  "Getafe": ["GET", "#005999", "#FFFFFF"],
  "Girona": ["GIR", "#CC0000", "#FFFFFF"],
  "Levante": ["LEV", "#004997", "#B4131E"],
  "Mallorca": ["MLL", "#E20613", "#000000"],
  "Málaga": ["MAL", "#00529F", "#FFFFFF"],
  "Osasuna": ["OSA", "#D91A21", "#0A346F"],
  "Racing Santander": ["RAC", "#009B48", "#FFFFFF"],
  "Rayo Vallecano": ["RAY", "#E53027", "#FFFFFF"],
  "Real Betis": ["BET", "#00954C", "#FFFFFF"],
  "Real Madrid": ["RMA", "#FEBE10", "#00529F"],
  "Real Oviedo": ["OVI", "#0B4EA2", "#FFFFFF"],
  "Real Sociedad": ["RSO", "#0067B1", "#FFFFFF"],
  "Sevilla": ["SEV", "#D80027", "#FFFFFF"],
  "Valencia": ["VAL", "#F18E00", "#000000"],
  "Villarreal": ["VIL", "#FFE667", "#005187"],

  // Italy
  "AC Milan": ["MIL", "#FB090B", "#000000"],
  "Atalanta": ["ATA", "#1E71B8", "#000000"],
  "Bologna": ["BOL", "#1A2F48", "#A21C2B"],
  "Cagliari": ["CAG", "#C8102E", "#0B2340"],
  "Como": ["COM", "#004B93", "#FFFFFF"],
  "Cremonese": ["CRE", "#D4021D", "#808080"],
  "Empoli": ["EMP", "#00579C", "#FFFFFF"],
  "Fiorentina": ["FIO", "#7B2A8C", "#FFFFFF"],
  "Frosinone": ["FRO", "#F9C81B", "#005CA9"],
  "Genoa": ["GEN", "#B01F24", "#00284A"],
  "Hellas Verona": ["VER", "#FFD400", "#0A2240"],
  "Internazionale": ["INT", "#0068A8", "#000000"],
  "Juventus": ["JUV", "#FFFFFF", "#000000"],
  "Lazio": ["LAZ", "#87D8F7", "#FFFFFF"],
  "Lecce": ["LEC", "#FFE500", "#D3122A"],
  "Monza": ["MON", "#E10E15", "#FFFFFF"],
  "Napoli": ["NAP", "#12A0D7", "#FFFFFF"],
  "Parma": ["PAR", "#FFE500", "#003C7D"],
  "Pisa": ["PIS", "#00539B", "#000000"],
  "Roma": ["ROM", "#8E1F2F", "#F0BC42"],
  "Sassuolo": ["SAS", "#00A752", "#000000"],
  "Torino": ["TOR", "#8A1B18", "#FFFFFF"],
  "Udinese": ["UDI", "#000000", "#FFFFFF"],
  "Venezia": ["VEN", "#000000", "#F58220"],

  // Germany
  "1. FC Köln": ["KOE", "#ED1C24", "#FFFFFF"],
  "Augsburg": ["FCA", "#BA3733", "#46714D"],
  "Bayer Leverkusen": ["B04", "#E32221", "#000000"],
  "Bayern Munich": ["FCB", "#DC052D", "#0066B2"],
  "Borussia Dortmund": ["BVB", "#FDE100", "#000000"],
  "Borussia Monchengladbach": ["BMG", "#000000", "#00A94F"],
  "Eintracht Frankfurt": ["SGE", "#E1000F", "#000000"],
  "Elversberg": ["ELV", "#E30613", "#FFFFFF"],
  "FC Schalke 04": ["S04", "#004D9D", "#FFFFFF"],
  "FSV Mainz 05": ["M05", "#C3141E", "#FFFFFF"],
  "Hamburger SV": ["HSV", "#0A57A4", "#000000"],
  "RB Leipzig": ["RBL", "#DD0741", "#001F47"],
  "SC Freiburg": ["SCF", "#000000", "#E2001A"],
  "SC Paderborn": ["SCP", "#004E9E", "#000000"],
  "TSG Hoffenheim": ["TSG", "#1961B5", "#FFFFFF"],
  "Union Berlin": ["FCU", "#EB1923", "#FFED00"],
  "VfB Stuttgart": ["VFB", "#E32219", "#FFFFFF"],
  "Werder Bremen": ["SVW", "#1D9053", "#FFFFFF"],

  // France
  "Angers": ["SCO", "#000000", "#FFFFFF"],
  "Auxerre": ["AUX", "#0072BC", "#FFFFFF"],
  "Brest": ["BRE", "#E2001A", "#FFFFFF"],
  "Le Havre": ["HAC", "#005BAA", "#87CEEB"],
  "Le Mans": ["LMN", "#E2001A", "#FFE500"],
  "Lens": ["RCL", "#FFE500", "#E2001A"],
  "Lille": ["LIL", "#E01E13", "#004170"],
  "Lorient": ["FCL", "#F58220", "#000000"],
  "Lyon": ["OL", "#1B3A6B", "#E2001A"],
  "Marseille": ["OM", "#2FAEE0", "#FFFFFF"],
  "Monaco": ["ASM", "#E63329", "#FFFFFF"],
  "Nice": ["NIC", "#E2001A", "#000000"],
  "Paris FC": ["PFC", "#00509E", "#FFFFFF"],
  "Paris Saint-Germain": ["PSG", "#004170", "#DA291C"],
  "Rennes": ["SRF", "#E23A2E", "#000000"],
  "Strasbourg": ["RCS", "#0072BC", "#FFFFFF"],
  "Toulouse": ["TFC", "#69236C", "#FFFFFF"],
  "Troyes": ["EST", "#1B4C9E", "#FFFFFF"],

  // Netherlands
  "ADO Den Haag": ["ADO", "#009B48", "#FFE500"],
  "AZ Alkmaar": ["AZ", "#E2001A", "#FFFFFF"],
  "Cambuur": ["CAM", "#FFE500", "#0072BC"],
  "Excelsior": ["EXC", "#E2001A", "#000000"],
  "Feyenoord": ["FEY", "#E2001A", "#FFFFFF"],
  "Fortuna Sittard": ["FOR", "#FFE500", "#009B48"],
  "Go Ahead Eagles": ["GAE", "#E2001A", "#FFE500"],
  "Groningen": ["GRO", "#009B48", "#FFFFFF"],
  "Heerenveen": ["HEE", "#0072BC", "#FFFFFF"],
  "NEC Nijmegen": ["NEC", "#E2001A", "#009B48"],
  "PEC Zwolle": ["PEC", "#0072BC", "#FFFFFF"],
  "PSV Eindhoven": ["PSV", "#E2001A", "#FFFFFF"],
  "Sparta Rotterdam": ["SPA", "#E2001A", "#FFFFFF"],
  "Utrecht": ["UTR", "#E2001A", "#FFFFFF"],

  // Portugal
  "Académico de Viseu": ["AVI", "#E2001A", "#000000"],
  "Alverca": ["ALV", "#E2001A", "#FFFFFF"],
  "Arouca": ["ARO", "#FFE500", "#0072BC"],
  "Benfica": ["SLB", "#E00000", "#FFFFFF"],
  "Casa Pia": ["CAS", "#000000", "#FFFFFF"],
  "Estoril": ["EST", "#FFE500", "#0072BC"],
  "Famalicão": ["FAM", "#0072BC", "#FFFFFF"],
  "Gil Vicente": ["GIL", "#E2001A", "#0072BC"],
  "Marítimo": ["MAR", "#009B48", "#E2001A"],
  "Moreirense": ["MOR", "#009B48", "#FFFFFF"],
  "Nacional": ["NAC", "#000000", "#FFFFFF"],
  "Porto": ["POR", "#0072BC", "#FFFFFF"],
  "Rio Ave": ["RIO", "#009B48", "#FFFFFF"],
  "Santa Clara": ["SAN", "#E2001A", "#FFFFFF"],
  "Sporting CP": ["SCP", "#008057", "#FFFFFF"],
  "Vitória SC": ["VIT", "#FFFFFF", "#000000"],
};

const NEUTRAL: ClubIdentity = { abbr: "", primary: "#4C5A70", secondary: "#8894A8" };

/**
 * A club we do not have colours for gets a neutral badge and initials taken
 * from its name. Inventing a colour would put Liverpool in blue, which is
 * worse than saying nothing.
 */
export function clubIdentity(name: string | null | undefined): ClubIdentity {
  if (!name) return { ...NEUTRAL, abbr: "?" };
  const hit = CLUBS[name];
  if (hit) return { abbr: hit[0], primary: hit[1], secondary: hit[2] };
  const initials = name
    .replace(/[^A-Za-zÀ-ÿ\s]/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 3)
    .map((w) => w[0].toUpperCase())
    .join("");
  return { ...NEUTRAL, abbr: initials || "?" };
}

const DARK = "#080B10";
const LIGHT = "#FFFFFF";

/**
 * Readable ink for text sitting on a club or competition colour.
 *
 * A luminance threshold is the obvious implementation and it is wrong: it put
 * white on Manchester City's sky blue at 2.5:1 and white on Arsenal's red at
 * 4.49:1. Compute both candidates and take the winner.
 */
export function inkOn(hex: string): string {
  return contrast(hex, DARK) >= contrast(hex, LIGHT) ? DARK : LIGHT;
}

/**
 * A badge fill and its ink, guaranteed to clear WCAG AA together.
 *
 * A handful of saturated mid-tones (Union Berlin's red, Arsenal's red) sit in
 * a band where neither black nor white reaches 4.5:1 against them. Rather than
 * ship an unreadable monogram or drop the club's colour, the fill is walked a
 * few percent toward whichever ink is already winning until it clears. The hue
 * survives; only lightness moves, and only as far as it has to.
 */
export function readableFill(hex: string, target = 4.5): { bg: string; ink: string } {
  const ink = inkOn(hex);
  const toward = ink === DARK ? 255 : 0; // push the fill away from the ink
  let bg = hex;
  for (let step = 0; step < 24 && contrast(bg, ink) < target; step++) {
    bg = mix(bg, toward, 0.04);
  }
  return { bg, ink };
}

function mix(hex: string, toward: number, amount: number): string {
  const ch = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  return (
    "#" +
    ch
      .map((c) => Math.round(c + (toward - c) * amount).toString(16).padStart(2, "0"))
      .join("")
  );
}

function relativeLuminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/* ---------------------------------------------------------------------------
   Competition atmosphere

   Generated, not illustrated. Two floodlight radials and a pitch-stripe
   gradient over the competition's own colour pair. It costs nothing to
   download, it changes with the calendar, and when there is licensed art the
   `art` field drops in behind it without touching a component.

   This lives here rather than beside the components because server components
   render it too, and a "use client" module cannot be imported into one.
--------------------------------------------------------------------------- */

export function competitionSurface(
  c: CompetitionIdentity,
  /**
   * How hard to darken the bottom of the frame. A full-bleed banner needs a
   * heavy floor for type to sit on; a 120px tile does not, and the same value
   * turns every small card to mud.
   */
  floor = 0.82,
): {
  backgroundColor: string;
  backgroundImage: string;
  backgroundSize: string;
  backgroundPosition: string;
} {
  return {
    backgroundColor: c.accent2,
    backgroundImage: [
      `radial-gradient(120% 90% at 12% -20%, ${c.accent}55 0%, transparent 55%)`,
      `radial-gradient(90% 80% at 92% -10%, ${c.accent}33 0%, transparent 60%)`,
      "repeating-linear-gradient(100deg, rgb(255 255 255 / 0.035) 0 22px, transparent 22px 44px)",
      `linear-gradient(180deg, transparent 30%, rgb(4 6 10 / ${floor}) 100%)`,
      c.art ? `url(${c.art})` : "",
    ]
      .filter(Boolean)
      .join(", "),
    backgroundSize: "cover",
    backgroundPosition: "center",
  };
}
