import pandas as pd
import re
import nltk
from nltk.corpus import stopwords, wordnet
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer

# === NLTK Resources ===
nltk.download('punkt')
nltk.download('stopwords')
nltk.download('wordnet')
nltk.download('omw-1.4')

# === Step 1: Load Data from direction checking output ===
input_path = (r"data/input_file.csv")
df = pd.read_csv(input_path)

# === Step 2: Preserve Original CMV Label ===
df['cmv_label_original'] = df['cmv_involved']

# === Step 3: Clean and Preprocess Narrative Column ===
df['narrative_clean'] = df['narrative'].fillna('').str.lower().str.replace(r'[^a-z0-9\s]', '', regex=True)
lemmatizer = WordNetLemmatizer()
stop_words = set(stopwords.words('english'))

def clean_and_lemmatize(text):
    tokens = word_tokenize(text, preserve_line=True)
    return [
        lemmatizer.lemmatize(word)
        for word in tokens
        if word.isalpha() and word not in stop_words
    ]

# === Step 4: Synonyms + Phrases ===
base_terms = ["truck", "trailer", "semi", "van", "freight", "tractor", "pickup", "cargo", "load", "hauler"]

def get_wordnet_synonyms(term):
    synonyms = set()
    for syn in wordnet.synsets(term, pos=wordnet.NOUN):
        for lemma in syn.lemmas():
            synonyms.add(lemma.name().replace('_', ' '))
    return synonyms

all_synonyms = set()
for term in base_terms:
    all_synonyms.update(get_wordnet_synonyms(term))

contextual_patterns = ["cargo spill", "jackknife", "overturned", "tanker", "box truck", "big rig", "commercial vehicle"]

def nlp_match_strong(text):
    tokens = clean_and_lemmatize(text)
    phrase_match = any(phrase in text for phrase in contextual_patterns)
    synonym_match = any(word in all_synonyms for word in tokens)
    return int(synonym_match or phrase_match)

df['nlp_cmv_match'] = df['narrative_clean'].apply(nlp_match_strong)

# === Step 5: Harmful Event Logic ===
harmful_cols = ['harmfuleventonedescription', 'harmfuleventtwodescription', 'mostharmfuleventdescription']
df['majority_other_vehicle'] = df[harmful_cols].apply(
    lambda row: sum(str(x).strip().lower() == 'other vehicle' for x in row) >= 2,
    axis=1
).astype(int)

# === Step 6: Vehicle Body Type Match ===
cmv_types = {
    "TRUCK - CARGO VAN/LIGHT 2 AXLES (OVER 10,000LBS (4,536 KG))",
    "TRUCK - TRACTOR",
    "TRUCK - OTHER LIGHT (10,000LBS (4,536KG) OR LESS)",
    "TRUCK - MEDIUM/HEAVY 3 AXLES (OVER 10,000LBS (4,536KG)",
    "FIRE VEHICLE/NON EMERGENCY",
    "FARM VEHICLE"
}
df['vehicle_type_cmv'] = df['vehicle_body_description'].isin(cmv_types).astype(int) if 'vehicle_body_description' in df.columns else 0

# === Step 7: Vehicle Make/Model Logic ===
cmv_makes = {
    "FREIGHTLINER", "FRHT", "FRHTLNR", "FRIEGHTLINER", "FRGHTLNR", "FRTLNR", "FREHT",
    "VOLVO", "VOV", "VNL", "VN", "VOLV",
    "KENWORTH", "KW", "KENILWORTH", "KENTWORTH",
    "PETERBILT", "PTRB", "PETERBUILT", "PTRBLT", "PET", "PETER",
    "INTERNATIONAL", "INTL", "INT", "INTERN", "INTERNATIONA",
    "MACK", "MAC",
    "ISUZU", "ISU",
    "STERLING", "WESTERN STAR", "HINO", "DODGE", "FORD", "GMC", "CHEVY", "RAM", "JOHN DEERE"
}

cmv_model_keywords = {
    "TT", "TRACTOR", "TRUCK", "BOX", "CASCADIA", "DUMP", "TOW", "TRAILER", "VNL",
    "CXU613", "TTQ", "DT", "TK", "TR", "PROSTAR", "T2000", "LT625", "LT", "TT26", "VNL64TRA",
    "VN VNL", "T680", "T880", "108SD", "PRO STAR", "ISX15", "FLATBED", "E250", "E450", "F550", "F350",
    "CA11", "FC2", "UTILITY", "CENTURY", "SEMI", "WORK", "DUMP TK", "BOX TK", "CARGO", "DAY", "MR600",
    "TRUCK TRACTOR", "TRACTOR TRAILER", "TRACTOR TRUCK"
}

def normalize(s):
    return str(s).strip().upper().replace("-", "").replace(" ", "")

def model_and_make_is_cmv(row):
    make = normalize(row.get("vehiclemake", ""))
    model = normalize(row.get("vehiclemodel", ""))
    return (
        make in cmv_makes and
        any(keyword in model for keyword in cmv_model_keywords)
    )

df['vehicle_make_model_cmv'] = df.apply(model_and_make_is_cmv, axis=1).astype(int)

# === Step 8: Harmful Event Keywords ===
cmv_event_terms = ['jackknife', 'spilled cargo']

def event_description_contains_cmv_term(row):
    for col in harmful_cols:
        value = str(row[col]).lower()
        if any(term in value for term in cmv_event_terms):
            return 1
    return 0

df['harmful_event_cmv_flag'] = df.apply(event_description_contains_cmv_term, axis=1).astype(int)

# === Step 9: Score + CMV Flag Logic ===
df['cmv_score'] = (
    df['vehicle_type_cmv'] * 10 +
    df['nlp_cmv_match'] * 3 +
    df['vehicle_make_model_cmv'] * 8 +
    df['majority_other_vehicle'] * 1 +
    df['harmful_event_cmv_flag'] * 10
)
df['cmv_inferred'] = df['cmv_score'] >= 10

# === Step 10: Overwrite cmv_involved if model says True (TP or FP)
df['cmv_involved'] = df['cmv_inferred']

# === Step 11: Evaluation Metrics ===
df['cmv_label_original'] = df['cmv_label_original'].astype(bool)
tp = ((df['cmv_involved'] == True) & (df['cmv_label_original'] == True)).sum()
fp = ((df['cmv_involved'] == True) & (df['cmv_label_original'] == False)).sum()
tn = ((df['cmv_involved'] == False) & (df['cmv_label_original'] == False)).sum()
fn = ((df['cmv_involved'] == False) & (df['cmv_label_original'] == True)).sum()

print("\n📈 Confusion Matrix Breakdown:")
print(f"✅ True Positives (TP): {tp}")
print(f"❌ False Positives (FP): {fp}")
print(f"✅ True Negatives (TN): {tn}")
print(f"❌ False Negatives (FN): {fn}")

precision = tp / (tp + fp) if (tp + fp) > 0 else 0
recall = tp / (tp + fn) if (tp + fn) > 0 else 0
f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

print("\n📊 Evaluation Metrics:")
print(f"Precision: {precision:.3f}")
print(f"Recall:    {recall:.3f}")
print(f"F1 Score:  {f1:.3f}")

# === Step 12: Update OBJECTID using Parking Lot logic ===
def extract_objectid(parking_lot):
    try:
        val = int(float(parking_lot))  # handles "10293.0"
        val_str = str(val)
        if len(val_str) <= 3:
            return str(int(val_str))  # force strip leading 0s
        elif len(val_str) == 5:
            return str(int(val_str[1:4]))  # middle 3 digits without leading 0s
        else:
            return str(val)
    except:
        return None

df['OBJECTID'] = df['Parking Lot'].apply(extract_objectid)


# === Step 13: Output File ===
output_path = r"data/output_file.csv"
df.to_csv(output_path, index=False)

# === Step 14: CMV Final Count ===
print("\n📊 CMV Inferred Counts (Final Updated Column):")
print(df['cmv_involved'].value_counts().rename(index={True: 'True (CMV Involved)', False: 'False (Not Involved)'}))
print(f"\n✅ Updated file saved with corrected 'cmv_involved' and 'OBJECTID' column:\n{output_path}")
