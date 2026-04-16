# Apollo Hackathon

## Overview

Apollo Hackathon is a prospecting and outreach application designed to help companies identify weaknesses in competitor offerings and turn those insights into targeted sales opportunities.

The platform works by analyzing competing companies, surfacing discrepancies or flaws in their products, services, or market positioning, and then using those findings to help generate persuasive outbound emails aimed at decision-makers such as CFOs, CTOs, and other high-level stakeholders. The goal is to help users position Apollo as a stronger alternative in a thoughtful and data-informed way.

---

## Core Idea

The application is built around a simple workflow:

1. The user inputs their **company** and **product**.
2. The user can then either:
   - manually enter an arbitrary number of competitor companies, or
   - allow the application to automatically generate a list of relevant competitors based on the user’s field or market.
3. The system researches those competitors by searching the web and scraping relevant public information such as articles, news, and other sources.
4. The application presents the findings back to the user, including visualizations such as graphs and charts for easier comparison and interpretation.
5. Based on the discovered weaknesses or discrepancies, the application generates tailored outreach emails intended for key decision-makers at those competitor companies’ customer organizations.
6. With the user’s approval, the application can then send those emails through the Gmail API.

---

## Features

- **Company and product input**
  - Users provide the name of their company and the product they want to position.

- **Competitor selection**
  - Users can manually enter any number of competitors.
  - Users can also choose automatic competitor discovery.
  - Due to current client-side limitations, the auto-generated company list is typically limited to around **6–8 companies**.

- **Web research and scraping**
  - The application searches the web for relevant information on selected competitors.
  - It gathers data from articles, public sources, and other relevant material.

- **Competitive analysis**
  - Surfaced findings focus on potential weaknesses, gaps, or discrepancies in competitor offerings.

- **Data visualization**
  - The application displays graphs and charts so users can better understand the competitive landscape and findings.

- **Email generation**
  - The system drafts persuasive emails tailored to the findings for each target company.

- **Gmail integration**
  - Through the Gmail API, the platform can prepare and send emails once the user explicitly consents.

---

## How It Works

### 1. User Input
The application first prompts the user to enter:
- their company name
- their product

### 2. Competitor Discovery
After that, the user chooses one of two paths:
- **Manual input:** enter competitor companies directly
- **Automatic generation:** let the application identify relevant competitors in the same field

### 3. Research and Analysis
The system then:
- searches the web for relevant competitor information
- scrapes useful public-facing content
- identifies issues, weaknesses, or discrepancies that may create an opening for Apollo

### 4. Visualization
The resulting insights are shown to the user through:
- summaries
- graphs
- charts
- other visual aids for comparison

### 5. Outreach Generation
Using the collected information, the application generates email drafts designed to appeal to high-level stakeholders such as:
- CFOs
- CTOs
- other decision-makers

### 6. Consent-Based Sending
Finally, after the user reviews and approves the content, the application can send the emails using the Gmail API.

---

## Use Case

This tool is meant to streamline competitor research and outbound sales outreach. Instead of manually researching multiple companies and drafting tailored sales emails one by one, users can rely on the platform to automate much of that workflow while still maintaining user approval before emails are sent.

---

## Current Constraints

- Automatic competitor generation is currently limited on the client side.
- In practice, this means the system typically generates about **6–8 relevant companies** at a time.
- Email sending only occurs **with user consent**.

---

## Tech Direction

This project is centered around:
- competitor discovery
- web search and scraping
- insight extraction
- chart/graph-based visualization
- AI-assisted email generation
- Gmail API integration for consent-based delivery

---

## Goal

The ultimate goal of Apollo Hackathon is to help users:
- identify opportunities in competitor weaknesses
- better understand their market landscape
- generate persuasive targeted outreach faster
- connect Apollo’s value proposition directly to the needs of high-level decision-makers

---

## Future Improvements

Potential next steps could include:
- improving the competitor discovery algorithm
- increasing the number of companies handled automatically
- refining the relevance and accuracy of scraped insights
- enhancing visualization dashboards
- adding deeper personalization for generated emails
- expanding integrations beyond Gmail