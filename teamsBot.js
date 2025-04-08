const { TeamsActivityHandler, CardFactory, TeamsInfo } = require('botbuilder');
const axios = require('axios');
const { v4: uuidv4 } = require('uuid');
const username = 'Convobi';
const password = 'CBMA@2024';
const credentials = Buffer.from(`${username}:${password}`).toString('base64');

const authorizedEmails = ['Chaula_Siddharth@comcast.com','alexw@example.com', 'AjitKumar_Sancheti@comcast.com','Deepak_BhatPalimar@comcast.com','Pachva_Dhanush@comcast.com'];

class TeamsBot extends TeamsActivityHandler {
    constructor() {
        super();

        // Handle members being added to the conversation
        this.onMembersAdded(async (context, next) => {
            const membersAdded = context.activity.membersAdded;
            for (let i = 0; i < membersAdded.length; i++) {
                if (membersAdded[i].id !== context.activity.recipient.id) {
                    await context.sendActivity("Hi, I am Ask Analytics - your smart assistant to answer any questions you have on SMB Sales and demand.");

                    const quickReplyCard = CardFactory.heroCard(
                        'FAQ\'s:',
                        null,
                        CardFactory.actions([
                            {
                                type: 'messageBack',
                                title: "BI Sales Trend in Last 6 Months",
                                displayText: "BI Sales Trend in Last 6 Months",
                                text: "BI Sales Trend in Last 6 Months",
                                value: { action: "question2" }
                            },
                            {
                                type: 'messageBack',
                                title: "CBM Lines Sold in H2 2024",
                                displayText: "CBM Lines Sold in H2 2024",
                                text: "CBM Lines Sold in H2 2024",
                                value: { action: "question3" }
                            },
                            {
                                type: 'messageBack',
                                title: "Sales from web leads",
                                displayText: "Sales from web leads",
                                text: "Sales from web leads",
                                value: { action: "question4" }
                            }
                        ])
                    );

                    await context.sendActivity({ attachments: [quickReplyCard] });
                }
            }

            await next();
        });
        
        // Handle messages from the user
        this.onMessage(async (context, next) => {
            let userMessage = context.activity.text;
            const userId = context.activity.from.id;
            const userName = context.activity.from.name;
            const uniqueId = uuidv4(); 
            let shortName;
            if (userName.includes(',')) {
                const parts = userName.split(',');
                const secondPart = parts[1].trim();
                shortName = secondPart.split(' ')[0];
            } else {
                const parts = userName.split(' ');
                if (parts.length > 1) {
                    const secondPart = parts[1].trim();
                    shortName = secondPart.split(' ')[0];
                } else {
                    shortName = userName;
                }
            }
            let userMail;
            try {
                const member = await TeamsInfo.getMember(context, userId);
                userMail = member.email || 'No email available';
                console.log(`Extracted email: ${userMail}`); // Print the extracted email
            } catch (error) {
                console.error('Error fetching member details:', error);
                userMail = 'No email available';
            }

            // Check if the email is authorized
            if (!authorizedEmails.includes(userMail)) {
                await context.sendActivity('YOU ARE NOT AUTHORIZED');
                return;
            }

            if (context.activity.value && context.activity.value.action) {
                switch (context.activity.value.action) {
                    case 'question2':
                        userMessage = "BI Sales Trend in Last 6 Months";
                        break;
                    case 'question3':
                        userMessage = "CBM Lines Sold in H2 2024";
                        break;
                    case 'question4':
                        userMessage = "Sales from web leads";
                        break;
                }

                await context.sendActivity({
                    from: { id: context.activity.from.id, name: context.activity.from.name },
                    text: userMessage
                });
            }

            if (userMessage.toLowerCase() === "frequently asked questions") {
                const quickReplyCard = CardFactory.heroCard(
                    'FAQ\'s:',
                    null,
                    CardFactory.actions([
                        {
                            type: 'messageBack',
                            title: "BI Sales Trend in Last 6 Months",
                            displayText: "BI Sales Trend in Last 6 Months",
                            text: "BI Sales Trend in Last 6 Months",
                            value: { action: "question2" }
                        },
                        {
                            type: 'messageBack',
                            title: "CBM Lines Sold in H2 2024",
                            displayText: "CBM Lines Sold in H2 2024",
                            text: "CBM Lines Sold in H2 2024",
                            value: { action: "question3" }
                        },
                        {
                            type: 'messageBack',
                            title: "Sales from web leads",
                            displayText: "Sales from web leads",
                            text: "Sales from web leads",
                            value: { action: "question4" }
                        }
                    ])
                );

                await context.sendActivity({ attachments: [quickReplyCard] });
            
            } 
            if (userMessage.toLowerCase() === "hi" || userMessage.toLowerCase() === "hello" || userMessage.toLowerCase() === "how are you" || userMessage.toLowerCase() === "good morning") {
                await context.sendActivity(`Hello, ${shortName}! How can I assist you today?`);
            }else {
                try {
                    const response = await axios.post('http://127.0.0.1:8050/gpt-request', {
                        prompt: userMessage,
                        userId: userId,
                        userName:userName,
                        uniqueId:uniqueId,
                        userMail:userMail
                    }, {
                        headers: {
                            'Authorization': `Basic ${credentials}`
                        }
                    });

                    // Check if the response contains a message field and it's not empty
                    if (response.data.message && response.data.message.trim() !== "") {
                        await context.sendActivity(response.data.message);
                    }

                    // Check if the response contains multiple adaptive cards
                    if (Array.isArray(response.data.response)) {
                        for (let i = 0; i < response.data.response.length; i++) {
                            const adaptiveCard = response.data.response[i];
                            if (adaptiveCard.type === 'AdaptiveCard') {
                                await context.sendActivity({
                                    attachments: [CardFactory.adaptiveCard(adaptiveCard)]
                                });

                                // Send the additional message after the first adaptive card
                                if (i === 0 && response.data.additional_message) {
                                    await context.sendActivity(response.data.additional_message);
                                }
                            }
                        }
                    } else if (response.data.response.type === 'AdaptiveCard') {
                        const adaptiveCard = response.data.response;
                        await context.sendActivity({
                            attachments: [CardFactory.adaptiveCard(adaptiveCard)]
                        });

                        // Send the additional message after the first adaptive card
                        if (response.data.additional_message) {
                            await context.sendActivity(response.data.additional_message);
                        }
                    } else {
                        await context.sendActivity(response.data.response);
                    }

                } catch (error) {
                    console.error('Error connecting to Python backend:', error);
                    await context.sendActivity('Sorry, there was an error processing your request.');
                }
            }

            await next();
        });
    }
}

module.exports.TeamsBot = TeamsBot;                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            