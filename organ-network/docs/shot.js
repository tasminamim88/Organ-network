const { chromium } = require('playwright');

const DATA = {
  '/hospitals': [
    { id: 1, name: 'Dhaka Medical College Hospital', city: 'Dhaka' },
    { id: 2, name: 'Square Hospital', city: 'Dhaka' },
  ],
  '/stats': { donors: 4, available_organs: 3, waiting_patients: 5, allocations: 1, transplants: 2 },
  '/organs/available': [
    { id: 10, donor_id: 1, organ_type: 'kidney', status: 'available', donor_group: 'O', donor_name: 'Rahim Uddin', created_at: '' },
    { id: 11, donor_id: 2, organ_type: 'liver', status: 'available', donor_group: 'A', donor_name: 'Sadia Islam', created_at: '' },
    { id: 12, donor_id: 1, organ_type: 'cornea', status: 'available', donor_group: 'O', donor_name: 'Rahim Uddin', created_at: '' },
  ],
  '/donors': [
    { id: 3, name: 'Kamal Hossain', blood_type: 'B', status: 'registered', created_at: '' },
  ],
  '/patients': [
    { id: 21, name: 'Nusrat Jahan', blood_type: 'AB', organ_needed: 'kidney', urgency: 5, status: 'waiting', registered_at: '2026-05-02' },
    { id: 22, name: 'Arif Chowdhury', blood_type: 'A', organ_needed: 'kidney', urgency: 3, status: 'waiting', registered_at: '2026-04-10' },
    { id: 23, name: 'Mitu Rani', blood_type: 'O', organ_needed: 'liver', urgency: 4, status: 'waiting', registered_at: '2026-06-01' },
  ],
  '/allocations': [
    { id: 5, organ_id: 9, patient_id: 20, status: 'allocated', organ_type: 'heart', donor_name: 'Jamal Mia', patient_name: 'Farhana Akter', created_at: '' },
    { id: 4, organ_id: 8, patient_id: 19, status: 'transplanted', organ_type: 'kidney', donor_name: 'Salma Begum', patient_name: 'Tanvir Ahmed', created_at: '' },
  ],
  '/organs/10/candidates': [
    { id: 21, name: 'Nusrat Jahan', blood_type: 'AB', organ_needed: 'kidney', urgency: 5, status: 'waiting', registered_at: '2026-05-02' },
    { id: 22, name: 'Arif Chowdhury', blood_type: 'A', organ_needed: 'kidney', urgency: 3, status: 'waiting', registered_at: '2026-04-10' },
  ],
};
const USER = { id: 1, name: 'Dr. Coordinator', email: 'admin@organnet.local', role: 'coordinator', created_at: '' };

(async () => {
  const port = process.env.PORT || '8130';
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1180, height: 1000 }, deviceScaleFactor: 2 });

  await page.addInitScript(([user, data]) => {
    try {
      localStorage.setItem('on_token', 'demo.token');
      localStorage.setItem('on_user', JSON.stringify(user));
    } catch (e) {}
    window.fetch = async (url) => {
      const path = String(url).split('?')[0].replace(/^https?:\/\/[^/]+/, '');
      const body = data[path] !== undefined ? data[path] : [];
      return { ok: true, status: 200, json: async () => body };
    };
  }, [USER, DATA]);

  await page.goto('http://localhost:' + port + '/index.html');
  await page.waitForSelector('.stat', { timeout: 5000 });
  await page.waitForTimeout(300);
  // open the Organs & Matching tab and show the engine in action
  await page.evaluate(() => window.showAppTab('organs'));
  await page.evaluate(() => window.findCandidates(10));
  await page.waitForTimeout(300);
  await page.screenshot({ path: __dirname + '/screenshot.png', fullPage: true });
  await browser.close();
  console.log('screenshot written');
})();
