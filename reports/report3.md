# Expedia Replica — Assignment 2 Part 1

## Repository and commit #DONE
Repository: https://github.com/dw477/expedia-replica

Commit: 8b10dea

## Research Notes
Research was limited to API functionality. With this, I found that Geoapify supported the hotel search functionality outright with limited extra integration. 

## Early Mockup
![Mockup](report-screenshots/mockup1.png)

This is a pre-development mockup displaying the position of the already developed zip-lookup tool over the proposed live hotel list and map representations. This layout was used in the final iteration.


## Video Demo
![User Interaction Demo](report-videos/recording2.mp4)

## Verification Record
This implementation is expected to get hotel results based on a zip code and display them alongside their coordinate locations on a map. In testing, the backend successfully pulled hotel location data based on the zip code input. The data collected was correctly listed and placed the hotels in their respecitve positions on the map.

ZIP 19380 was tested on 9/29/26 and successfully pulled two results within 5km.



## AI Disclosure and Evidence Log
OpenAI's GPT-6 Sol model was used to generate code for this project.

The following is one of the prompts used:

> read readme.md and agents.md.
> CHECK:
> - whether the repository can support a Leaflet map. if not, report what must be done.
> TAKE ACTION:
> - create a Leatlet map that displays the returned hotels alongside the list of hotels
> - selecting a hotel in either display selects it in the other
> do not make backend changes. only work within the frontend. do not make assumptions. pause to clarify if needed.

This prompt was used to connect the backend hotel lookup function to the frontend. This allowed the frontend to display the data gathered in a list alongside the Leaflet map.