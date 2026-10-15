"""
Extra companies for the live job scan, taken from the NextLeet company list (api.nextleet.com/api/all-companies,
470 companies) and kept only when:
  1. a public job board was found and verified to have India openings (probed 2026-10-16), and
  2. the company's typical India fresher (new-grad SDE) CTC is >= 15 LPA.

`est_ctc` is an ESTIMATED fresher band from public reports, not an offer figure; the UI must label it "est.".
Companies whose fresher band is usually below 15 LPA (e.g. services firms) are deliberately left out.
Format: (display name, board, token, est_ctc)
"""

NEXTLEET_COMPANIES = [
    # Big tech / large product
    ("LinkedIn", "lever", "linkedin", "35-50 LPA"), ("Stripe", "greenhouse", "stripe", "40-60 LPA"),
    ("Databricks", "greenhouse", "databricks", "35-55 LPA"), ("Snowflake", "ashby", "snowflake", "35-50 LPA"),
    ("ServiceNow", "smartrecruiters", "servicenow", "20-30 LPA"), ("Okta", "greenhouse", "okta", "20-30 LPA"),
    ("MongoDB", "greenhouse", "mongodb", "25-35 LPA"), ("Coupang", "greenhouse", "coupang", "25-40 LPA"),
    ("DoorDash", "greenhouse", "doordashindia", "30-45 LPA"), ("Airbnb", "greenhouse", "airbnb", "35-50 LPA"),
    ("Coinbase", "greenhouse", "coinbase", "35-50 LPA"), ("Roblox", "greenhouse", "roblox", "35-50 LPA"),
    ("OpenAI", "ashby", "openai", "40+ LPA"), ("Waymo", "greenhouse", "waymo", "35+ LPA"),
    ("ByteDance", "smartrecruiters", "bytedance", "25-40 LPA"), ("Spotify", "lever", "spotify", "25-35 LPA"),
    ("Agoda", "greenhouse", "agoda", "25-35 LPA"), ("Grab", "smartrecruiters", "grab", "20-30 LPA"),
    ("Datadog", "greenhouse", "datadog", "30-45 LPA"), ("Twilio", "greenhouse", "twilio", "25-35 LPA"),
    ("Arista Networks", "smartrecruiters", "aristanetworks", "25-35 LPA"), ("Pure Storage", "greenhouse", "purestorage", "25-35 LPA"),
    ("Zscaler", "greenhouse", "zscaler", "20-30 LPA"), ("Rubrik", "greenhouse", "rubrik", "30-45 LPA"),
    ("Netskope", "greenhouse", "netskope", "20-30 LPA"), ("Smartsheet", "greenhouse", "smartsheet", "20-30 LPA"),
    ("Toast", "greenhouse", "toast", "20-30 LPA"), ("GoDaddy", "greenhouse", "godaddy", "18-25 LPA"),
    ("Wise", "smartrecruiters", "wise", "20-30 LPA"), ("Flexport", "greenhouse", "flexport", "20-30 LPA"),
    ("Coursera", "greenhouse", "coursera", "18-25 LPA"), ("UiPath", "ashby", "uipath", "15-25 LPA"),
    ("Samsara", "greenhouse", "samsara", "25-35 LPA"), ("Sumo Logic", "greenhouse", "sumologic", "18-25 LPA"),
    ("Zynga", "greenhouse", "zyngacareers", "18-25 LPA"), ("Roku", "greenhouse", "roku", "20-30 LPA"),
    ("Notion", "ashby", "notion", "30+ LPA"), ("Mixpanel", "greenhouse", "mixpanel", "20-30 LPA"),
    ("Deliveroo", "greenhouse", "deliveroo", "20-30 LPA"), ("Axon", "greenhouse", "axon", "20-30 LPA"),
    ("Scale AI", "greenhouse", "scaleai", "30+ LPA"), ("Duolingo", "greenhouse", "duolingo", "25+ LPA"),
    ("Mapbox", "ashby", "mapbox", "20-30 LPA"), ("Harness", "greenhouse", "harnessinc", "20-30 LPA"),
    ("Apollo.io", "greenhouse", "apolloio", "20-30 LPA"), ("EarnIn", "greenhouse", "earnin", "20-30 LPA"),
    ("BitGo", "greenhouse", "bitgo", "20-30 LPA"), ("Airwallex", "ashby", "airwallex", "20-30 LPA"),
    ("Poshmark", "ashby", "poshmark", "15-25 LPA"), ("Druva", "greenhouse", "druva", "15-22 LPA"),
    ("PubMatic", "greenhouse", "pubmatic", "15-22 LPA"), ("InMobi", "greenhouse", "inmobi", "18-28 LPA"),
    ("DevRev", "greenhouse", "devrev", "20-30 LPA"), ("Tekion", "ashby", "tekion", "18-28 LPA"),
    ("StackAdapt", "greenhouse", "stackadapt", "15-25 LPA"),
    # Indian product companies
    ("Swiggy", "smartrecruiters", "swiggy", "18-28 LPA"), ("Meesho", "lever", "meesho", "20-30 LPA"),
    ("CRED", "lever", "cred", "25-35 LPA"), ("Groww", "greenhouse", "groww", "20-30 LPA"),
    ("Zeta", "lever", "zeta", "18-28 LPA"), ("Mindtickle", "lever", "mindtickle", "15-22 LPA"),
    ("Paytm", "lever", "paytm", "15-20 LPA"), ("FreshWorks", "smartrecruiters", "freshworks", "15-20 LPA"),
    # Quant / trading
    ("Tower Research Capital", "greenhouse", "towerresearchcapital", "40+ LPA"), ("IMC", "greenhouse", "imc", "40+ LPA"),
    ("Squarepoint Capital", "greenhouse", "squarepointcapital", "35+ LPA"), ("WorldQuant", "greenhouse", "worldquant", "25+ LPA"),
    ("Point72", "greenhouse", "point72", "30+ LPA"), ("Jump Trading", "greenhouse", "jumptrading", "40+ LPA"),
]

EST_CTC = {name: band for name, _board, _token, band in NEXTLEET_COMPANIES}
