/* support library for gardening UI */
GITHUB_API_URL_BASE = 'https://api.github.com/repos/';

var addLabel = function(issue_url, label) {
  var url = issue_url + '/labels';
  console.log('post: ' + url);
  fetch(url, {
    method: 'POST',
    credentials: 'include',
    body: JSON.stringify({'labels': [label]}),
    headers: {
      'Content-Type': 'application/json'
    }
  }).then((response) => {
    return response.json();
  }).then((response) => {
      console.log(JSON.stringify(response));
    }
  ).catch((error) => {
    console.log('label update failed, you may have to authenticate at github.com:' + error.message);
    // TODO(aiuto): The notify locks up the browser. It is too invasive for
    // people to use it right now.
    // increaseBackoff();
  });
};

var removeLabel = function(issue_url, label) {
  console.log('Remove label: ' + label);
};

replaceLabel = function(issue_url, oldLabel, newLabel) {
  addLabel(issue_url, newLabel);
  removeLabel(issue_url, oldLabel);
};
