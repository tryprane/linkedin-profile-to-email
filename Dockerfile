FROM apify/actor-python-playwright:3.11

# Copy requirements and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install patchright and playwright browser binaries
RUN patchright install chromium || true
RUN playwright install chromium --with-deps

# Copy project files
COPY . ./

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Command to run the Actor
CMD ["python3", "-m", "src.main"]
