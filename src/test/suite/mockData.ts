// Import necessary modules to read environment variables
export const mockConfig = {
    username: process.env.MOCK_USERNAME || 'default-username', // fallback for development/testing
    password: process.env.MOCK_PASSWORD || 'default-password',
    region: process.env.MOCK_REGION || 'ous'
};

export const mockGlucoseReading = {
    value: 5.5,
    trend: 'FLAT'
};
