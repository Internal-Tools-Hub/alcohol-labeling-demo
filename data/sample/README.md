# Alcohol Label Image Generator

This script generates test images for alcohol labeling compliance testing using Google's Gemini image generation API.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up Google AI API key:
```bash
export GOOGLE_API_KEY="your-api-key-here"
```

## Usage

Generate images for all categories:
```bash
python generate.py --all
```

Generate images for specific categories:
```bash
python generate.py --beer
python generate.py --wine
python generate.py --liquor
```

Overwrite existing images:
```bash
python generate.py --all --overwrite
python generate.py --beer --overwrite
```

By default, the script will skip existing images unless the `--overwrite` flag is used.

## Output

The script will generate images in the following structure:
```
data/sample/
├── beer/
│   ├── pass/
│   │   ├── front/     # 10 compliant beer front labels
│   │   └── back/      # 10 compliant beer back labels
│   └── fail/
│       ├── front/     # 10 non-compliant beer front labels
│       └── back/      # 10 non-compliant beer back labels
├── wine/
│   ├── pass/
│   │   ├── front/     # 10 compliant wine front labels
│   │   └── back/      # 10 compliant wine back labels
│   └── fail/
│       ├── front/     # 10 non-compliant wine front labels
│       └── back/      # 10 non-compliant wine back labels
└── liquor/
    ├── pass/
    │   ├── front/     # 10 compliant liquor front labels
    │   └── back/      # 10 compliant liquor back labels
    └── fail/
        ├── front/     # 10 non-compliant liquor front labels
        └── back/      # 10 non-compliant liquor back labels
```

### Label Content Distribution

**Front Labels** contain mandatory information that must appear in the same field of vision:
- Brand name
- Class/Type designation  
- Alcohol content
- Product description

**Back Labels** contain regulatory information that can appear on any label:
- Net contents
- Name and address
- Health warning statement
- Country of origin (liquor)
- Age statement (liquor)
- Vintage year (wine)
- Appellation (wine)
- Varietal (wine)
- Brewery information (beer)

## Test Data

Each category includes:
- **Pass scenarios**: Labels that comply with all regulatory requirements
- **Fail scenarios**: Labels that violate specific regulatory citations (27 CFR requirements)

The fail scenarios cover common violations like:
- Missing alcohol content statements
- Incorrect net contents declarations
- Missing brand names or required information
- Text size violations
- Missing government warnings
- Prohibited health claims

## Regulatory Citations

- **Beer**: 27 CFR 7.22
- **Wine**: 27 CFR 4.32  
- **Liquor**: 27 CFR 5.32
