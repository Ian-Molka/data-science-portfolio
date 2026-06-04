import streamlit as st
import tempfile
from pathlib import Path
from conflation_engine import run_conflation

st.title("Structure Tone Excel Conflation Tool")

st.write("Upload the PM Submittal file and the Master Material Tracking Log.")

source_file = st.file_uploader("Upload PM Submittal Import Excel", type=["xlsx"])
target_file = st.file_uploader("Upload Master Material Tracking Log", type=["xlsx"])

target_sheet = st.selectbox(
    "Choose target sheet",
    ["Hotel Infrastructure", "Hotel Fitout"]
)

if st.button("Run Conflation"):
    if source_file is None or target_file is None:
        st.error("Please upload both Excel files.")
    else:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            source_path = tmpdir / source_file.name
            target_path = tmpdir / target_file.name
            output_path = tmpdir / "Updated_Master_Log.xlsx"

            source_path.write_bytes(source_file.read())
            target_path.write_bytes(target_file.read())

            try:
                run_conflation(
                    source_path=source_path,
                    target_path=target_path,
                    output_path=output_path,
                    target_sheet=target_sheet
                )

                st.success("Conflation completed successfully!")

                with open(output_path, "rb") as f:
                    st.download_button(
                        label="Download Updated Excel File",
                        data=f,
                        file_name="Updated_Master_Log.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

            except Exception as e:
                st.error(f"Something went wrong: {e}")
