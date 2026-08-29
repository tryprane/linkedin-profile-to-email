FROM apify/actor-python-playwright:3.11

# Upgrade build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install Scrapling stealth browser binaries
RUN scrapling install || (patchright install chromium && playwright install chromium --with-deps)

# Copy application files
COPY . ./

# Environment configuration
ENV PYTHONUNBUFFERED=1

# Command to execute Actor
CMD ["python3", "-m", "src.main"]
