variable "name" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

variable "enable_guardduty" {
  type    = bool
  default = false
}

variable "enable_cloudtrail" {
  type    = bool
  default = false
}
