FROM mcr.microsoft.com/playwright:focal

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
RUN python -m playwright install

COPY primelooter.py primelooter.py
CMD [ "python", "primelooter.py" , "--loop" ]