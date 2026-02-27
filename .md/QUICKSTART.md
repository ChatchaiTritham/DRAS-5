# TRI-X Quick Start Guide

Get up and running with TRI-X in **5 minutes**!

## Prerequisites

- Python 3.8 or higher
- pip package manager
- Virtual environment (recommended)

## Step 1: Clone Repository

```bash
git clone https://github.com/ChatchaiTritham/TRI-X.git
cd TRI-X
```

## Step 2: Create Virtual Environment

### Windows
```bash
python -m venv venv
venv\Scripts\activate
```

### Linux/Mac
```bash
python -m venv venv
source venv/bin/activate
```

## Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 4: Install TRI-X Package

```bash
pip install -e .
```

## Step 5: Run Demo

### Command Line Demo
```bash
python scripts/demo.py
```

### Jupyter Notebook
```bash
jupyter lab notebooks/01_trix_introduction.ipynb
```

### Python API
```python
from trix import TRIXPipeline, TriageModule, TiTrATEEngine, XAIInterface, SRGL

# Initialize components
triage = TriageModule(threshold=0.7)
titrate = TiTrATEEngine(max_time=5.0)
xai = XAIInterface()
governance = SRGL()

# Create pipeline
pipeline = TRIXPipeline(triage, titrate, xai, governance)

# Process patient data
patient_data = {
 "features": {
 "urgency": 0.85,
 "severity": 0.78,
 "complexity": 0.65
 },
 "metadata": {
 "patient_id": "PT-001",
 "chief_complaint": "chest_pain"
 }
}

result = pipeline.process(patient_data)

# View results
print(f"Risk Level: {result.triage.risk_level.name}")
print(f"Risk Score: {result.triage.risk_score:.3f}")
print(f"Decision: {result.final_decision}")
print(f"\nExplanation:")
for feature, importance in sorted(
 result.explanation.feature_importance.items(),
 key=lambda x: x[1],
 reverse=True
)[:5]:
 print(f" {feature}: {importance:.3f}")
```

## Step 6: Run Tests (Optional)

```bash
pytest tests/ -v
```

## Next Steps

- 📖 Read the [full documentation](docs/API.md)
- 🔬 Explore [Jupyter notebooks](notebooks/)
- 🤝 Check [contributing guidelines](CONTRIBUTING.md)
- 🐛 Report issues on [GitHub](https://github.com/ChatchaiTritham/TRI-X/issues)

## Troubleshooting

### Issue: Import errors
**Solution**: Make sure you've installed the package with `pip install -e .`

### Issue: Missing dependencies
**Solution**: Reinstall requirements: `pip install -r requirements.txt --upgrade`

### Issue: Jupyter kernel not found
**Solution**:
```bash
python -m ipykernel install --user --name=trix
```

## Getting Help

- 📧 Email: chatchait66@nu.ac.th
- 💬 Discussions: https://github.com/ChatchaiTritham/TRI-X/discussions
- 🐛 Issues: https://github.com/ChatchaiTritham/TRI-X/issues

---

**Ready in 5 minutes!** ⏱️
