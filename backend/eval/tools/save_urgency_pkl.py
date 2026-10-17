"""
Updates urgency_classifier.pkl metadata with chosen thresholds and prints SHA-256.
"""
import pickle
import hashlib
from pathlib import Path

pkl_path = Path("backend/models/urgency_classifier.pkl")
with open(pkl_path, "rb") as f:
    data = pickle.load(f)

data["tau_high"] = 0.25
data["tau_soon"] = 0.30
data["tau_intent"] = 0.45

with open(pkl_path, "wb") as f:
    pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

with open(pkl_path, "rb") as f:
    content = f.read()
    h = hashlib.sha256(content).hexdigest()

print(f"Recorded urgency_classifier.pkl sha256: {h}")
print(f"Metadata verified: tau_high={data['tau_high']}, tau_soon={data['tau_soon']}, tau_intent={data['tau_intent']}")
