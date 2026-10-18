// A plugin whose page code fails: the page must report it and go on.
export default function activate() {
  throw new Error('e2e-broken refuses to start');
}
