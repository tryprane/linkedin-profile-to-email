FROM apify/actor-python-playwright:3.11

# Upgrade pip and install wheel
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install core stealth dependencies explicitly
RUN pip install --no-cache-dir curl_cffi==0.14.0 patchright==1.56.0 scrapling==0.4

# Copy requirements and install the rest
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and Patchright Chromium binaries
RUN patchright install chromium || true
RUN playwright install chromium --with-deps

# Copy project files
COPY . ./

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Command to run the Actor
CMD ["python3", "-m", "src.main"]
