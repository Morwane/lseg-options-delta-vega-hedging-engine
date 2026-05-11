import lseg.data as ld

RIC = "SPYD292650000.U"

SNAPSHOT_FIELDS = [
    "BID",
    "ASK",
    "TRDPRC_1",
    "CF_LAST",
    "CF_BID",
    "CF_ASK",
    "CF_CLOSE",
    "TR.PriceClose",
    "TR.BIDPRICE",
    "TR.ASKPRICE",
    "TR.ImpliedVolatility",
    "TR.Delta",
    "TR.Gamma",
    "TR.Vega",
    "TR.Theta",
    "TR.Rho",
    "TR.OPWCloseDelta",
    "TR.OPWCloseGamma",
    "TR.OPWCloseVega",
    "TR.OPWCloseTheta",
    "TR.OPWCloseRho",
    "TR.EXCHANGEPROVIDEDIMPLIEDVOLATILITY",
]

print("Opening LSEG session...")
ld.open_session()

print("\n" + "=" * 90)
print("1) SNAPSHOT / GET_DATA TEST")
print("=" * 90)

for field in SNAPSHOT_FIELDS:
    try:
        df = ld.get_data(
            universe=[RIC],
            fields=[field],
        )
        if isinstance(df, tuple):
            df = df[0]
        status = "OK" if df is not None and not df.empty else "EMPTY"
        print(f"{field:42s} -> {status}")
        if df is not None and not df.empty:
            print(df)
    except Exception as e:
        print(f"{field:42s} -> ERROR {str(e)[:180]}")

print("\n" + "=" * 90)
print("2) HISTORICAL / GET_HISTORY TEST")
print("=" * 90)

for field in SNAPSHOT_FIELDS:
    try:
        df = ld.get_history(
            universe=[RIC],
            fields=[field],
            interval="daily",
            count=20,
        )
        status = "OK" if df is not None and not df.empty else "EMPTY"
        print(f"{field:42s} -> {status:5s} rows={0 if df is None else len(df)}")
        if df is not None and not df.empty:
            print(df.tail(3))
    except Exception as e:
        print(f"{field:42s} -> ERROR {str(e)[:180]}")

ld.close_session()
print("\nDone.")
