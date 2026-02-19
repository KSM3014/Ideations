@echo off
cd /d "C:\Users\Administrator\Desktop\Projects\IDEATIONs\idea generator"
python -c "import sys; sys.path.insert(0,'.'); sys.path.insert(0,'.claude/skills/publisher/scripts'); from report_generator import ReportGenerator; ReportGenerator().generate_daily(); ReportGenerator().generate_weekly()"
