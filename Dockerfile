FROM apify/actor-python-playwright:3.11

# Install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install the browser build used by Scrapling.
RUN scrapling install

# Copy application files
COPY . ./

# Environment configuration
ENV PYTHONUNBUFFERED=1

# Command to execute Actor
CMD ["python3", "-m", "src.main"]
