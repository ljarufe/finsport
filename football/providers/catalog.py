"""Static competition catalogue for approved historical providers."""

EUROPE_COMPETITIONS = {
    ("DE", "Bundesliga"): "DEU Bundesliga 1",
    ("EN", "Premier League"): "ENG Premier League",
    ("ES", "La Liga"): "ESP La Liga",
    ("FR", "Ligue 1"): "FRA Ligue 1",
    ("IT", "Serie A"): "ITA Serie A",
    ("NL", "Eredivisie"): "NLD Eredivisie",
    ("PT", "Primeira Liga"): "PRT Liga 1",
    ("TR", "Süper Lig"): "TUR Super Lig",
}

DIRECT_COMPETITIONS = {
    ("AR", "Liga Profesional Argentina"): (
        "ARG",
        "https://www.football-data.co.uk/new/ARG.csv",
    ),
    ("BR", "Serie A"): ("BRA", "https://www.football-data.co.uk/new/BRA.csv"),
    ("US", "Major League Soccer"): (
        "USA",
        "https://www.football-data.co.uk/new/USA.csv",
    ),
}
