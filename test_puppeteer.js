const puppeteer = require('puppeteer');

(async () => {
    const browser = await puppeteer.launch({headless: true});
    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36');
    console.log("Navigating...");
    const response = await page.goto('https://www.wedmegood.com/vendors/ahmedabad/wedding-venues/?page=5', { waitUntil: 'domcontentloaded' });
    console.log("HTTP Status:", response.status());
    const content = await page.content();
    console.log("Content length:", content.length);
    console.log("Found PrimaryVendorCard:", content.includes('PrimaryVendorCard'));
    await browser.close();
})();
