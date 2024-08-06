# Use the official Python image from the Docker Hub
FROM python:3.12

# Set environment variables to avoid Python buffering
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file to the working directory
COPY requirements.txt /app/

# Install the dependencies
RUN pip install -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . /app/

# Run the Django development server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
