import pandas as pd

TYPE_MAP = {
    "Analog In": "REAL",
    "Analog Out": "REAL",
    "Digital In": "BOOL",
    "Digital Out": "BOOL"
}

def parse_excel(file_path="variable1.xlsx"):
    df = pd.read_excel(file_path)
    df = df.rename(columns=lambda x: x.strip())

    variables = []
    for _, row in df.iterrows():
        tag = str(row["Tag"]).strip() if pd.notna(row["Tag"]) else ""
        io_type = str(row["IO_Type"]).strip() if pd.notna(row["IO_Type"]) else ""
        desc = str(row["Description"]).strip() if pd.notna(row["Description"]) else ""
        tank = str(row["Tank"]).strip() if "Tank" in df.columns and pd.notna(row["Tank"]) else ""
        io = str(row["Inputs/Output"]).strip() if "Inputs/Output" in df.columns and pd.notna(row["Inputs/Output"]) else ""

        if not tag or not io_type:
            continue

        st_type = TYPE_MAP.get(io_type, "BOOL")

        variables.append({
            "name": tag,
            "type": st_type,
            "comment": desc,
            "tank": tank,
            "io_type": io_type
        })
    return variables
