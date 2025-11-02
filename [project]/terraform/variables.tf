variable "linode_token" {
  type        = string
  description = "Linode API token"
}

variable "root_pass" {
  type        = string
  description = "Root password for the Linode instance"
}

variable "ssh_key_id" {
  type        = string
  description = "ID of the SSH key to be used for authentication"
}

variable "cloudflare_inbound_rules" {
  type = list(object({
    label    = string
    action   = string
    protocol = string
    ports    = string
    ipv4     = list(string)
    ipv6     = list(string)
  }))
  default = []
  description = "List of Cloudflare inbound firewall rules"
}

variable "developer_inbound_ips" {
  type = list(object({
    label    = string
    action   = string
    protocol = string
    ports    = string
    ipv4     = list(string)
    ipv6     = list(string)
  }))
  default = []
  description = "List of inbound firewall rules"
}

variable "gh_actions_ipv4" {
  type        = list(string)
  default = []
  description = "List of GitHub Actions IPv4 CIDRs"
}

variable "gh_actions_ipv6" {
  type        = list(string)
  default = []
  description = "List of GitHub Actions IPv6 CIDRs"
}

variable "gh_actions_inbound_rules" {
  type = list(object({
    label    = string
    action   = string
    protocol = string
    ports    = string
    ipv4     = list(string)
    ipv6     = list(string)
  }))
  default = []
  description = "A list of allowed inbound IPs for trusted Github API IPs"
}

variable "project_inbound_rules" {
  type = list(object({
    label    = string
    action   = string
    protocol = string
    ports    = string
    ipv4     = list(string)
    ipv6     = list(string)
  }))
  default = []
  description = "A list of allowed inbound IPs for HTTPs connections (i.e. project.com)"
}

