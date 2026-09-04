
#!/usr/bin/env python3



import tempfile

from pathlib import Path



import intelligence

from intelligence import build_intelligence



intelligence.INTELLIGENCE_FILE = (
    Path(tempfile.gettempdir()) / "nodesmart-test-intelligence.json"
)





SCENARIOS = {

    "NORMAL": {

        "status": "healthy",

        "health": {

            "asterisk": "normal",

            "internet": "normal",

            "cpu": "normal",

            "memory": "normal",

            "disk": "normal",

        },

        "health_reasons": [],

        "asterisk": "online",

        "internet": "online",

    },



    "CPU WARNING": {

        "status": "degraded",

        "health": {

            "asterisk": "normal",

            "internet": "normal",

            "cpu": "warning",

            "memory": "normal",

            "disk": "normal",

        },

        "health_reasons": [

            "CPU temperature elevated (74.0 C)"

        ],

        "asterisk": "online",

        "internet": "online",

    },



    "MULTIPLE WARNINGS": {

        "status": "degraded",

        "health": {

            "asterisk": "normal",

            "internet": "normal",

            "cpu": "warning",

            "memory": "warning",

            "disk": "normal",

        },

        "health_reasons": [

            "CPU temperature elevated (74.0 C)",

            "Memory usage elevated (82.0%)"

        ],

        "asterisk": "online",

        "internet": "online",

    },



    "CRITICAL": {

        "status": "fault",

        "health": {

            "asterisk": "critical",

            "internet": "normal",

            "cpu": "normal",

            "memory": "normal",

            "disk": "normal",

        },

        "health_reasons": [

            "Asterisk is offline"

        ],

        "asterisk": "offline",

        "internet": "online",

    },

}





for name, state in SCENARIOS.items():



    result = build_intelligence(state)



    print("=" * 60)

    print(name)

    print("=" * 60)



    print("Level:", result.get("level"))

    print("Attention:", result.get("attention_required"))



    recommendation = result.get("recommendation", {})



    print("Priority:", recommendation.get("priority"))

    print("Action required:", recommendation.get("action_required"))

    print("Recommendation:", recommendation.get("message"))



    print("Summary:", result.get("summary"))

    print()
